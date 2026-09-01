from __future__ import annotations

from collections.abc import Iterable

from .support import ArchiveSink, AuditRow, FormattedRecord, Formatter


class AuditExporter:
    def __init__(self, formatter: Formatter, sink: ArchiveSink, *, chunk_size: int = 128) -> None:
        if chunk_size < 1:
            raise ValueError("chunk_size must be positive")
        self._formatter = formatter
        self._sink = sink
        self._chunk_size = chunk_size

    def export(self, rows: Iterable[AuditRow]) -> int:
        buffer: list[FormattedRecord] = []
        exported = 0
        for row in rows:
            buffer.append(self._formatter.format(row))
            if len(buffer) == self._chunk_size:
                self._sink.write(buffer)
                exported += len(buffer)
                buffer.clear()
        if buffer:
            self._sink.write(buffer)
            exported += len(buffer)
        return exported
