from __future__ import annotations

from collections.abc import Iterable

from .support import ArchiveSink, AuditRow, Formatter


class AuditExporter:
    def __init__(self, formatter: Formatter, sink: ArchiveSink, *, chunk_size: int = 128) -> None:
        if chunk_size < 1:
            raise ValueError("chunk_size must be positive")
        self._formatter = formatter
        self._sink = sink
        self._chunk_size = chunk_size

    def export(self, rows: Iterable[AuditRow]) -> int:
        # BUG: chunked writes do not help when both complete collections are
        # materialized before the first write.
        source_rows = list(rows)
        records = [self._formatter.format(row) for row in source_rows]
        for offset in range(0, len(records), self._chunk_size):
            self._sink.write(records[offset:offset + self._chunk_size])
        return len(records)
