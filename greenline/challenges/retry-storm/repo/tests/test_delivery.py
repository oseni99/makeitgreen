import pytest

from delivery import DeliveryRejected, Response, RetryExhausted, deliver


class Sender:
    def __init__(self, statuses: list[Response]):
        self.responses = iter(statuses)
        self.calls = 0

    def __call__(self) -> Response:
        self.calls += 1
        return next(self.responses)


def test_success_does_not_retry_or_sleep() -> None:
    sender = Sender([Response(204, {})])
    sleeps: list[float] = []
    assert deliver(sender, sleeps.append).status == 204
    assert sender.calls == 1
    assert sleeps == []


def test_transient_failures_back_off_then_succeed() -> None:
    sender = Sender([Response(503, {}), Response(503, {}), Response(200, {})])
    sleeps: list[float] = []
    assert deliver(sender, sleeps.append, base_delay=0.5).status == 200
    assert sleeps == [0.5, 1.0]


def test_retry_after_overrides_client_backoff() -> None:
    sender = Sender([Response(429, {"Retry-After": "7"}), Response(200, {})])
    sleeps: list[float] = []
    deliver(sender, sleeps.append)
    assert sleeps == [7.0]


@pytest.mark.parametrize("status", [400, 401, 404, 500])
def test_permanent_response_is_not_retried(status: int) -> None:
    sender = Sender([Response(status, {}), Response(200, {})])
    with pytest.raises(DeliveryRejected, match=str(status)):
        deliver(sender, lambda _: None)
    assert sender.calls == 1


def test_attempt_budget_has_no_extra_call_or_sleep() -> None:
    sender = Sender([Response(503, {}), Response(503, {}), Response(200, {})])
    sleeps: list[float] = []
    with pytest.raises(RetryExhausted):
        deliver(sender, sleeps.append, max_attempts=2, base_delay=5)
    assert sender.calls == 2
    assert sleeps == [5.0]


def test_exponential_delay_is_capped() -> None:
    sender = Sender([Response(503, {})] * 5)
    sleeps: list[float] = []
    with pytest.raises(RetryExhausted):
        deliver(sender, sleeps.append, max_attempts=5, base_delay=3, max_delay=5)
    assert sleeps == [3.0, 5.0, 5.0, 5.0]
