from __future__ import annotations

from threading import Event

from run_jobs import OUTPUT_LIMIT, RunJobStore


def test_job_streams_incremental_output_and_releases_once() -> None:
    store = RunJobStore(workers=1)
    emitted = Event()
    finish = Event()
    released = Event()
    releases: list[str] = []

    def release() -> None:
        releases.append("released")
        released.set()

    def work(emit):
        emit("collecting…\n")
        emitted.set()
        assert finish.wait(timeout=2)
        emit("done\n")
        return {"green": True, "output": "collecting…\ndone\n"}

    started = store.start("demo", work, release=release)
    assert emitted.wait(timeout=1)
    first = store.get(started["job_id"])
    assert first is not None
    assert first["status"] == "running"
    assert first["output"] == "collecting…\n"

    finish.set()
    assert released.wait(timeout=1)
    final = store.get(started["job_id"], after=first["next_offset"])
    assert final is not None
    assert final["result"]["green"] is True
    assert releases == ["released"]


def test_job_offsets_remain_absolute_when_output_is_truncated() -> None:
    store = RunJobStore(workers=1)
    finished = Event()

    def work(emit):
        emit("a" * (OUTPUT_LIMIT + 50))
        finished.set()
        return {"green": False, "output": "a" * OUTPUT_LIMIT}

    started = store.start("large", work, release=lambda: None)
    assert finished.wait(timeout=1)
    snapshot = store.get(started["job_id"], after=0)
    assert snapshot is not None
    assert snapshot["output_truncated"] is True
    assert len(snapshot["output"]) == OUTPUT_LIMIT
    assert snapshot["next_offset"] == OUTPUT_LIMIT + 50
