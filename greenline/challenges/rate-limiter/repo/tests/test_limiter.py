from __future__ import annotations

import threading

import pytest

from limiter import RateLimiter


class Clock:
    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class SequenceClock:
    def __init__(self, values: list[float]) -> None:
        self._values = iter(values)
        self._lock = threading.Lock()

    def __call__(self) -> float:
        with self._lock:
            return next(self._values)


class ReverseArrivalGate:
    """Hold the first caller until the second caller completes admission."""

    def __init__(self) -> None:
        self.first_waiting = threading.Event()
        self.release_first = threading.Event()

    def wait(self, timeout: float | None = None) -> None:
        if threading.current_thread().name == "first-arrival":
            self.first_waiting.set()
            if not self.release_first.wait(timeout):
                raise TimeoutError("first caller was not released")


def test_sequential_limit_and_window_expiry() -> None:
    clock = Clock()
    limiter = RateLimiter(limit=2, window_seconds=10, clock=clock)

    assert limiter.allow("acme") is True
    assert limiter.allow("acme") is True
    assert limiter.allow("acme") is False

    clock.now = 110.0
    assert limiter.allow("acme") is True


def test_rejects_invalid_configuration_and_tenant() -> None:
    clock = Clock()
    with pytest.raises(ValueError):
        RateLimiter(limit=0, window_seconds=10, clock=clock)
    with pytest.raises(ValueError):
        RateLimiter(limit=1, window_seconds=0, clock=clock)
    with pytest.raises(ValueError):
        RateLimiter(limit=1, window_seconds=10, clock=clock).allow("")


@pytest.mark.parametrize("limit", [1, 2, 3, 4, 5])
def test_tenants_have_independent_allowances(limit: int) -> None:
    limiter = RateLimiter(limit=limit, window_seconds=60, clock=Clock())

    for _ in range(limit):
        assert limiter.allow("noisy") is True
    assert limiter.allow("quiet") is True
    assert limiter.allow("noisy") is False


@pytest.mark.parametrize(
    ("workers", "limit"),
    [(3, 1), (4, 1), (4, 2), (6, 2), (8, 3)],
)
def test_concurrent_decision_never_exceeds_limit(workers: int, limit: int) -> None:
    gate = threading.Barrier(workers)
    limiter = RateLimiter(
        limit=limit,
        window_seconds=60,
        clock=Clock(),
        decision_gate=gate,
    )
    results: list[bool] = []
    errors: list[BaseException] = []

    def attempt() -> None:
        try:
            results.append(limiter.allow("acme"))
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=attempt) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)

    assert errors == []
    assert all(not thread.is_alive() for thread in threads)
    assert results.count(True) == limit
    assert results.count(False) == workers - limit


@pytest.mark.parametrize(
    ("timestamps", "window_seconds"),
    [([100.0, 105.0, 111.0], 10), ([0.0, 4.0, 6.0], 5), ([20.0, 29.0, 31.0], 10)],
)
def test_timestamps_are_sampled_in_atomic_admission_order(
    timestamps: list[float], window_seconds: float
) -> None:
    gate = ReverseArrivalGate()
    clock = SequenceClock(timestamps)
    limiter = RateLimiter(
        limit=2,
        window_seconds=window_seconds,
        clock=clock,
        decision_gate=gate,  # type: ignore[arg-type]
    )
    results: list[bool] = []

    first = threading.Thread(
        target=lambda: results.append(limiter.allow("acme")),
        name="first-arrival",
    )
    second = threading.Thread(
        target=lambda: results.append(limiter.allow("acme")),
        name="second-arrival",
    )
    first.start()
    assert gate.first_waiting.wait(1)
    second.start()
    second.join(timeout=1)
    assert not second.is_alive()
    gate.release_first.set()
    first.join(timeout=1)
    assert not first.is_alive()
    assert results == [True, True]

    # At t=111 the admission recorded at t=100 has expired, while t=105 remains.
    # A deque ordered by atomic admission time must prune the expired entry.
    limiter.decision_gate = None
    assert limiter.allow("acme") is True
