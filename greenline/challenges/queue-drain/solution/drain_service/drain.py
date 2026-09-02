from collections.abc import Callable, Iterable
from typing import Any


def drain(events: Iterable[dict[str, Any]], process: Callable[[dict[str, Any]], None]) -> tuple[list[str], list[str]]:
    processed: list[str] = []
    quarantined: list[str] = []
    for event in events:
        event_id = event["id"]
        if not isinstance(event.get("payload"), dict):
            quarantined.append(event_id)
            continue
        process(event)
        processed.append(event_id)
    return processed, quarantined
