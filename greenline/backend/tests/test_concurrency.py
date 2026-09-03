from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event

import pytest

import app as api
import challenge_locks
from execution_fakes import FunctionExecutionAdapter
from learner_state import WorkspaceSnapshot


def _record_run(operations: list[str]):
    def _mock(slug: str, _user_id: str | None, **_kwargs) -> dict:
        operations.append("record_run")
        return {"id": 1, "slug": slug}

    return _mock


def test_reset_waits_for_in_flight_run_and_is_the_final_operation(monkeypatch) -> None:
    run_started = Event()
    allow_run_to_finish = Event()
    reset_requested = Event()
    operations: list[str] = []

    monkeypatch.setattr(api.ch, "load", lambda slug: {"slug": slug})

    def blocked_run(slug: str) -> dict:
        operations.append("run")
        run_started.set()
        assert allow_run_to_finish.wait(timeout=2)
        return {"green": True, "passed": 1, "failed": 0, "errors": 0, "skipped": 0,
                "exit_code": 0, "output": "", "tests": []}

    monkeypatch.setattr(
        api,
        "execution_adapter",
        FunctionExecutionAdapter(
            lambda run, _on_output: blocked_run(run.slug)
        ),
    )
    monkeypatch.setattr(
        api.learner_state_adapter,
        "snapshot",
        lambda slug, user_id: WorkspaceSnapshot(0, {}),
    )
    monkeypatch.setattr(
        api.learner_state_adapter, "record_run", _record_run(operations)
    )
    monkeypatch.setattr(
        api.learner_state_adapter,
        "reset",
        lambda slug, user_id: operations.append("reset_state"),
    )

    def request_reset() -> dict:
        reset_requested.set()
        return api.reset("same-challenge")

    with ThreadPoolExecutor(max_workers=2) as pool:
        run_future = pool.submit(api.run, "same-challenge")
        assert run_started.wait(timeout=1)
        reset_future = pool.submit(request_reset)
        assert reset_requested.wait(timeout=1)

        with pytest.raises(TimeoutError):
            reset_future.result(timeout=0.1)

        allow_run_to_finish.set()
        run_result = run_future.result(timeout=1)
        assert run_result["green"] is True
        assert "run" in run_result
        assert reset_future.result(timeout=1) == {"ok": True}

    assert operations == ["run", "record_run", "reset_state"]
    assert challenge_locks._entries == {}


def test_save_waits_for_in_flight_run(monkeypatch) -> None:
    run_started = Event()
    allow_run_to_finish = Event()
    save_requested = Event()
    operations: list[str] = []

    monkeypatch.setattr(api.ch, "load", lambda slug: {"slug": slug})

    def blocked_run(slug: str) -> dict:
        operations.append("run")
        run_started.set()
        assert allow_run_to_finish.wait(timeout=2)
        return {"green": False, "passed": 0, "failed": 1, "errors": 0, "skipped": 0,
                "exit_code": 1, "output": "", "tests": []}

    monkeypatch.setattr(
        api,
        "execution_adapter",
        FunctionExecutionAdapter(
            lambda run, _on_output: blocked_run(run.slug)
        ),
    )
    monkeypatch.setattr(
        api.learner_state_adapter,
        "snapshot",
        lambda slug, user_id: WorkspaceSnapshot(0, {}),
    )
    monkeypatch.setattr(
        api.learner_state_adapter, "record_run", _record_run(operations)
    )
    monkeypatch.setattr(
        api.learner_state_adapter,
        "write_file",
        lambda slug, path, content, user_id: operations.append("write_file"),
    )

    def request_save() -> dict:
        save_requested.set()
        return api.put_file(
            "same-challenge", "src/service.py", api.FileBody(content="updated")
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        run_future = pool.submit(api.run, "same-challenge")
        assert run_started.wait(timeout=1)
        save_future = pool.submit(request_save)
        assert save_requested.wait(timeout=1)

        with pytest.raises(TimeoutError):
            save_future.result(timeout=0.1)

        allow_run_to_finish.set()
        assert run_future.result(timeout=1)["green"] is False
        assert save_future.result(timeout=1) == {"ok": True}

    assert operations == ["run", "record_run", "write_file"]
    assert challenge_locks._entries == {}


def test_different_challenges_do_not_block_each_other(monkeypatch) -> None:
    run_started = Event()
    allow_run_to_finish = Event()
    operations: list[str] = []

    monkeypatch.setattr(api.ch, "load", lambda slug: {"slug": slug})

    def blocked_run(slug: str) -> dict:
        run_started.set()
        assert allow_run_to_finish.wait(timeout=2)
        return {"green": False, "passed": 0, "failed": 1, "errors": 0, "skipped": 0,
                "exit_code": 1, "output": "", "tests": []}

    monkeypatch.setattr(
        api,
        "execution_adapter",
        FunctionExecutionAdapter(
            lambda run, _on_output: blocked_run(run.slug)
        ),
    )
    monkeypatch.setattr(
        api.learner_state_adapter,
        "snapshot",
        lambda slug, user_id: WorkspaceSnapshot(0, {}),
    )
    monkeypatch.setattr(
        api.learner_state_adapter,
        "record_run",
        lambda slug, user_id, **_kwargs: {"id": 1},
    )
    monkeypatch.setattr(
        api.learner_state_adapter,
        "reset",
        lambda slug, user_id: operations.append(f"reset:{slug}"),
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        run_future = pool.submit(api.run, "challenge-a")
        assert run_started.wait(timeout=1)

        reset_future = pool.submit(api.reset, "challenge-b")
        assert reset_future.result(timeout=1) == {"ok": True}

        allow_run_to_finish.set()
        assert run_future.result(timeout=1)["green"] is False

    assert operations == ["reset:challenge-b"]
    assert challenge_locks._entries == {}
