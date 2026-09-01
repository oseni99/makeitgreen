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
