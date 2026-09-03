"""Behavioral contracts for Learner State Adapters."""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

import challenges
import learner_state
import progress


@pytest.fixture
def challenge_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    slug = f"state-contract-{uuid4().hex}"
    challenge = tmp_path / "challenges" / slug
    repo = challenge / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    (challenge / "challenge.json").write_text(
        json.dumps(
            {
                "title": "State contract",
                "type": "Test",
                "difficulty": "Easy",
                "creatable": ["src/"],
            }
        ),
        encoding="utf-8",
    )
    (repo / "src" / "answer.py").write_text("answer = 'red'\n", encoding="utf-8")
    (repo / "tests" / "test_answer.py").write_text("def test_answer(): pass\n")
    monkeypatch.setattr(challenges, "CHALLENGES_DIR", tmp_path / "challenges")
    monkeypatch.setattr(challenges, "WORKSPACES_DIR", tmp_path / "workspaces")
    monkeypatch.setattr(progress, "DB_PATH", tmp_path / "progress.db")
    return slug


def _assert_contract(
    state: learner_state.LearnerStateAdapter,
    slug: str,
    user_a: str,
    user_b: str,
) -> None:
    state.write_file(slug, "src/answer.py", "answer = 'green'\n", user_a)
    state.create_file(slug, "src/extra.py", "extra = True\n", user_a)

    assert state.read_file(slug, "src/answer.py", user_a) == "answer = 'green'\n"
    assert state.read_file(slug, "src/answer.py", user_b) == "answer = 'red'\n"
    snapshot = state.snapshot(slug, user_a)
    assert snapshot.revision >= 0
    assert snapshot.files == {
        "src/answer.py": "answer = 'green'\n",
        "src/extra.py": "extra = True\n",
    }

    state.record_run(slug, user_a, green=False, failed=1, output="red")
    state.record_run(slug, user_a, green=True, passed=1, output="green")
    marked = state.mark_spoiled(slug, user_a)
    assert marked["status"] == "solved"
    assert marked["attempts"] == 2
    assert marked["spoiled"] is True
    assert [run["green"] for run in state.list_runs(slug, 10, user_a)] == [
        True,
        False,
    ]
    assert state.get_all(user_b) == {}

    state.reset(slug, user_a)
    assert state.snapshot(slug, user_a).files == {}
    assert state.get_all(user_a) == {}
    assert state.list_runs(slug, 10, user_a) == []


def test_local_adapter_satisfies_learner_state_contract(challenge_catalog: str) -> None:
    _assert_contract(
        learner_state.LocalLearnerStateAdapter(),
        challenge_catalog,
        "local-user-a",
        "local-user-b",
    )


@pytest.mark.skipif(
    not os.environ.get("GREENLINE_TEST_DATABASE_URL"),
    reason="requires a migrated PostgreSQL integration database",
)
def test_postgres_adapter_satisfies_learner_state_contract(
    challenge_catalog: str,
) -> None:
    adapter = learner_state.PostgresLearnerStateAdapter.connect(
        os.environ["GREENLINE_TEST_DATABASE_URL"]
    )
    try:
        suffix = uuid4().hex
        _assert_contract(
            adapter,
            challenge_catalog,
            f"postgres-user-a-{suffix}",
            f"postgres-user-b-{suffix}",
        )
    finally:
        adapter.close()


def test_postgres_adapter_refuses_anonymous_state_without_querying() -> None:
    adapter = learner_state.PostgresLearnerStateAdapter(pool=object())

    with pytest.raises(learner_state.LearnerIdentityRequired):
        adapter.get_all(None)
