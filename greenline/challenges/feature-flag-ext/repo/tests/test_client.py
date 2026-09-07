import pytest

from flag_source import MemoryFlagSource, Snapshot


def client(source, clock, ttl=30):
    try:
        from flag_runtime import FlagClient
    except ModuleNotFoundError:
        pytest.fail("create flag_runtime with FlagClient")
    return FlagClient(source, clock=clock, ttl_seconds=ttl)


@pytest.mark.parametrize(
    ("values", "key", "default", "expected"),
    [
        ({"search": True}, "search", False, True),
        ({"search": False}, "search", True, False),
        ({"search": True}, "missing", False, False),
        ({"search": False}, "missing", True, True),
    ],
)
def test_first_evaluation_fetches_and_missing_flag_uses_default(
    values: dict[str, bool], key: str, default: bool, expected: bool
) -> None:
    source = MemoryFlagSource({"prod": Snapshot(1, values)})
    flags = client(source, lambda: 100)
    assert flags.enabled("prod", key, default=default) is expected
    assert source.calls == ["prod"]


@pytest.mark.parametrize("ttl", [0.5, 1, 5, 30])
def test_snapshot_is_reused_until_ttl_expires(ttl: float) -> None:
    now = [10.0]
    source = MemoryFlagSource({"prod": Snapshot(1, {"search": False})})
    flags = client(source, lambda: now[0], ttl=ttl)
    assert flags.enabled("prod", "search") is False
    source.snapshots["prod"] = Snapshot(2, {"search": True})
    now[0] = 10.0 + ttl - 0.001
    assert flags.enabled("prod", "search") is False
    now[0] = 10.0 + ttl
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


@pytest.mark.parametrize(
    ("first_environment", "second_environment"),
    [("dev", "prod"), ("preview", "prod"), ("staging", "production")],
)
def test_environment_snapshots_are_isolated(
    first_environment: str, second_environment: str
) -> None:
    source = MemoryFlagSource({
        first_environment: Snapshot(1, {"agent": True}),
        second_environment: Snapshot(7, {"agent": False}),
    })
    flags = client(source, lambda: 0)
    assert flags.enabled(first_environment, "agent") is True
    assert flags.enabled(second_environment, "agent") is False
    assert source.calls == [first_environment, second_environment]


@pytest.mark.parametrize("ttl", [0, -1, -0.01])
def test_invalid_ttl_is_rejected(ttl: float) -> None:
    source = MemoryFlagSource({})
    with pytest.raises(ValueError, match="ttl_seconds"):
        client(source, lambda: 0, ttl=ttl)
