from __future__ import annotations

import gc
import weakref
from collections.abc import Iterator


class SinkFailure(RuntimeError):
    pass


class AuditRow:
    def __init__(self, sequence: int) -> None:
        self.sequence = sequence


class FormattedRecord:
    def __init__(self, text: str) -> None:
        self.text = text


class ObjectTracker:
    def __init__(self) -> None:
        self.rows: weakref.WeakSet[AuditRow] = weakref.WeakSet()
        self.records: weakref.WeakSet[FormattedRecord] = weakref.WeakSet()
        self.max_live_rows = 0
        self.max_live_records = 0

    def observe(self) -> None:
        gc.collect()
        self.max_live_rows = max(self.max_live_rows, len(self.rows))
        self.max_live_records = max(self.max_live_records, len(self.records))


class RowSource:
    def __init__(self, count: int, tracker: ObjectTracker) -> None:
        self.count = count
        self.tracker = tracker
        self.consumed = 0
        self._iterated = False

    def __iter__(self) -> Iterator[AuditRow]:
        if self._iterated:
            raise RuntimeError("result set cannot be rewound")
        self._iterated = True
        for sequence in range(self.count):
            row = AuditRow(sequence)
            self.tracker.rows.add(row)
            self.consumed += 1
            yield row


class Formatter:
    def __init__(self, tracker: ObjectTracker) -> None:
        self.tracker = tracker

    def format(self, row: AuditRow) -> FormattedRecord:
        record = FormattedRecord(f"{row.sequence},audit-event-{row.sequence}\n")
        self.tracker.records.add(record)
        return record


class ArchiveSink:
    def __init__(self, tracker: ObjectTracker, *, fail_on_call: int | None = None) -> None:
        self.tracker = tracker
        self.fail_on_call = fail_on_call
        self.calls = 0
        self.chunks: list[str] = []

    def write(self, records: list[FormattedRecord]) -> None:
        self.calls += 1
        self.tracker.observe()
        if self.fail_on_call == self.calls:
            raise SinkFailure("archive upload failed")
        self.chunks.append("".join(record.text for record in records))
