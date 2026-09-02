from copy import deepcopy
from typing import Any


def merge_config(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_config(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result
