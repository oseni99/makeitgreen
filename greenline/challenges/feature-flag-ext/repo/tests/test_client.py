import pytest

from flag_source import MemoryFlagSource, Snapshot


def client(source, clock, ttl=30):
    try:
        from flag_runtime import FlagClient
    except ModuleNotFoundError:
        pytest.fail("create flag_runtime with FlagClient")
    return FlagClient(source, clock=clock, ttl_seconds=ttl)


def test_first_evaluation_fetches_and_missing_flag_uses_default() -> None:
    source = MemoryFlagSource({"prod": Snapshot(1, {"search": True})})
    flags = client(source, lambda: 100)
    assert flags.enabled("prod", "search") is True
    assert flags.enabled("prod", "missing", default=False) is False
    assert source.calls == ["prod"]


def test_snapshot_is_reused_until_ttl_expires() -> None:
    now = [10.0]
    source = MemoryFlagSource({"prod": Snapshot(1, {"search": False})})
    flags = client(source, lambda: now[0], ttl=5)
    assert flags.enabled("prod", "search") is False
    source.snapshots["prod"] = Snapshot(2, {"search": True})
    now[0] = 14.9
    assert flags.enabled("prod", "search") is False
    now[0] = 15.0
    assert flags.enabled("prod", "search") is True
    assert source.calls == ["prod", "prod"]


def test_refresh_failure_uses_last_known_good_but_cold_failure_surfaces() -> None:
    now = [0.0]
    source = MemoryFlagSource({"prod": Snapshot(1, {"checkout": True})})
    flags = client(source, lambda: now[0], ttl=1)
    assert flags.enabled("prod", "checkout") is True
    source.failure = RuntimeError("control plane unavailable")
    now[0] = 2.0
    assert flags.enabled("prod", "checkout") is True

    cold = client(source, lambda: 2.0, ttl=1)
    with pytest.raises(RuntimeError, match="control plane"):
        cold.enabled("prod", "checkout")


def test_environment_snapshots_are_isolated() -> None:
    source = MemoryFlagSource({
        "dev": Snapshot(1, {"agent": True}),
        "prod": Snapshot(7, {"agent": False}),
    })
    flags = client(source, lambda: 0)
    assert flags.enabled("dev", "agent") is True
    assert flags.enabled("prod", "agent") is False
    assert source.calls == ["dev", "prod"]


def test_invalid_ttl_is_rejected() -> None:
    source = MemoryFlagSource({})
    with pytest.raises(ValueError, match="ttl_seconds"):
        client(source, lambda: 0, ttl=0)
