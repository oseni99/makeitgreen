from __future__ import annotations

import pytest

from archive import ArchiveSink, AuditExporter, Formatter, ObjectTracker, RowSource, SinkFailure


def setup(count: int, *, chunk_size: int = 128, fail_on_call: int | None = None):
    tracker = ObjectTracker()
    source = RowSource(count, tracker)
    sink = ArchiveSink(tracker, fail_on_call=fail_on_call)
    exporter = AuditExporter(Formatter(tracker), sink, chunk_size=chunk_size)
    return tracker, source, sink, exporter


def test_output_is_exact_and_in_source_order() -> None:
    _, source, sink, exporter = setup(5, chunk_size=2)

    assert exporter.export(source) == 5
    assert "".join(sink.chunks) == "".join(
        f"{index},audit-event-{index}\n" for index in range(5)
    )
    assert [chunk.count("\n") for chunk in sink.chunks] == [2, 2, 1]


def test_empty_source_performs_no_upload() -> None:
    _, source, sink, exporter = setup(0)

    assert exporter.export(source) == 0
    assert sink.calls == 0


@pytest.mark.parametrize("count", [1, 128, 129, 4097])
def test_live_objects_stay_bounded_by_chunk_size(count: int) -> None:
    tracker, source, _, exporter = setup(count)

    exporter.export(source)

    assert tracker.max_live_rows <= 2
    assert tracker.max_live_records <= 128


def test_sink_failure_stops_consuming_the_forward_only_source() -> None:
    _, source, _, exporter = setup(10_000, chunk_size=64, fail_on_call=2)

    with pytest.raises(SinkFailure):
        exporter.export(source)

    assert source.consumed <= 128


def test_source_is_consumed_only_once() -> None:
    _, source, _, exporter = setup(3, chunk_size=2)

    exporter.export(source)

    with pytest.raises(RuntimeError, match="cannot be rewound"):
        list(source)


@pytest.mark.parametrize(
    ("count", "chunk_size"),
    [(2, 1), (3, 2), (17, 4), (257, 128)],
)
def test_first_upload_does_not_retain_later_rows_or_records(
    count: int, chunk_size: int
) -> None:
    tracker, source, _, exporter = setup(count, chunk_size=chunk_size)

    exporter.export(source)

    assert tracker.max_live_rows <= 2
    assert tracker.max_live_records <= chunk_size


@pytest.mark.parametrize("fail_on_call", [1, 2, 3])
def test_each_failed_upload_stops_before_reading_the_next_chunk(
    fail_on_call: int,
) -> None:
    chunk_size = 4
    _, source, _, exporter = setup(
        100, chunk_size=chunk_size, fail_on_call=fail_on_call
    )

    with pytest.raises(SinkFailure):
        exporter.export(source)

    assert source.consumed <= fail_on_call * chunk_size
