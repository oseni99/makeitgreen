from config_service.merge import merge_config


def test_nested_values_merge() -> None:
    assert merge_config({"db": {"host": "localhost", "port": 5432}}, {"db": {"host": "db"}}) == {
        "db": {"host": "db", "port": 5432}
    }


def test_false_and_zero_are_real_overrides() -> None:
    defaults = {"debug": True, "workers": 4, "label": "prod"}
    assert merge_config(defaults, {"debug": False, "workers": 0, "label": ""}) == {
        "debug": False,
        "workers": 0,
        "label": "",
    }


def test_inputs_are_not_mutated() -> None:
    defaults = {"feature": {"enabled": True}}
    overrides = {"feature": {"enabled": False}}
    merge_config(defaults, overrides)
    assert defaults == {"feature": {"enabled": True}}
    assert overrides == {"feature": {"enabled": False}}
