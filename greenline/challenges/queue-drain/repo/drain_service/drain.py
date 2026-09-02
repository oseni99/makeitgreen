from collections.abc import Callable, Iterable
from typing import Any


def drain(events: Iterable[dict[str, Any]], process: Callable[[dict[str, Any]], None]) -> tuple[list[str], list[str]]:
    processed: list[str] = []
    quarantined: list[str] = []
    for event in events:
        event_id = event["id"]
        try:
            if not isinstance(event.get("payload"), dict):
                raise ValueError("payload must be an object")
            process(event)
            processed.append(event_id)
        except ValueError:
            quarantined.append(event_id)
            break
    return processed, quarantined
