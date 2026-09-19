import pytest

from cdc_log import CDCLog


def populated() -> CDCLog:
    log = CDCLog()
    for value in ["a", "b", "c", "d"]:
        log.append(value)
    return log


def test_slot_polls_in_sequence_and_resumes_after_ack() -> None:
    log = populated()
    log.create_slot("search")
    assert [c.sequence for c in log.poll("search", 2)] == [1, 2]
    log.acknowledge("search", 2)
    assert [c.sequence for c in log.poll("search", 10)] == [3, 4]


def test_fast_consumer_cannot_compact_past_slow_consumer() -> None:
    log = populated()
    log.create_slot("search")
    log.create_slot("analytics")
    log.poll("search", 4)
    log.acknowledge("search", 4)
    log.poll("analytics", 1)
    log.acknowledge("analytics", 1)
    assert log.compact() == 1
    assert log.retained_sequences == [2, 3, 4]
    assert [c.sequence for c in log.poll("analytics", 10)] == [2, 3, 4]


def test_ack_cannot_skip_beyond_delivered_range() -> None:
    log = populated()
    log.create_slot("search")
    log.poll("search", 2)
    with pytest.raises(ValueError, match="delivered"):
        log.acknowledge("search", 4)
    assert [c.sequence for c in log.poll("search", 10)] == [1, 2, 3, 4]


def test_acknowledgement_is_monotonic() -> None:
    log = populated()
    log.create_slot("search")
    log.poll("search", 3)
    log.acknowledge("search", 3)
    with pytest.raises(ValueError, match="backwards"):
        log.acknowledge("search", 2)


def test_dropping_abandoned_slot_releases_retention() -> None:
    log = populated()
    log.create_slot("search")
    log.create_slot("abandoned")
    log.poll("search", 4)
    log.acknowledge("search", 4)
    assert log.compact() == 0
    log.drop_slot("abandoned")
    assert log.compact() == 4
    assert log.retained_sequences == []


def test_unknown_and_duplicate_slots_are_rejected() -> None:
    log = CDCLog()
    log.create_slot("search")
    with pytest.raises(ValueError, match="exists"):
        log.create_slot("search")
    with pytest.raises(KeyError):
        log.poll("missing", 1)
    with pytest.raises(KeyError):
        log.drop_slot("missing")


@pytest.mark.parametrize("delivered,future", [(0, 1), (1, 2), (2, 4)])
def test_acknowledgement_cannot_move_past_each_delivered_boundary(
    delivered: int, future: int
) -> None:
    log = populated()
    log.create_slot("search")
    log.poll("search", delivered)

    with pytest.raises(ValueError, match="delivered"):
        log.acknowledge("search", future)


@pytest.mark.parametrize("acknowledged,backwards", [(2, 0), (3, 1)])
def test_acknowledgement_cannot_move_backwards_from_prior_progress(
    acknowledged: int, backwards: int
) -> None:
    log = populated()
    log.create_slot("search")
    log.poll("search", acknowledged)
    log.acknowledge("search", acknowledged)

    with pytest.raises(ValueError, match="backwards"):
        log.acknowledge("search", backwards)


@pytest.mark.parametrize("slow_ack", [0, 1, 2])
def test_compaction_uses_the_slowest_of_three_active_slots(slow_ack: int) -> None:
    log = populated()
    for name in ("fast", "middle", "slow"):
        log.create_slot(name)
    for name, acknowledged in (("fast", 4), ("middle", 3), ("slow", slow_ack)):
        log.poll(name, acknowledged)
        log.acknowledge(name, acknowledged)

    assert log.compact() == slow_ack
    assert log.retained_sequences == list(range(slow_ack + 1, 5))


def test_poll_rejects_negative_limit() -> None:
    log = populated()
    log.create_slot("search")
    with pytest.raises(ValueError, match="negative"):
        log.poll("search", -1)
