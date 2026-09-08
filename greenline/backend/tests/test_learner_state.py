"""Behavioral contracts for Learner State Adapters."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
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
    assert state.get_preferences(user_a) == {"prep_path": None}
    assert state.set_prep_path(user_a, "distributed") == {
        "prep_path": "distributed"
    }
    assert state.get_preferences(user_a) == {"prep_path": "distributed"}
    assert state.get_preferences(user_b) == {"prep_path": None}

    first_visit = datetime(2026, 9, 3, 12, tzinfo=timezone.utc)
    state.record_visit(user_a, first_visit)
    state.record_visit(user_a, first_visit)
    state.record_visit(user_a, datetime(2026, 9, 4, 12, tzinfo=timezone.utc))

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

    with pytest.raises(learner_state.DebriefRequiresSolved):
        state.save_debrief(
            slug,
            user_a,
            root_cause="A race",
            fix_reasoning="The lock makes the mutation atomic.",
            tradeoff="The critical section reduces concurrency.",
            useful=True,
            feedback="",
        )

    first_run = state.record_run(
        slug,
        user_a,
        green=False,
        failed=1,
        output="red",
        workspace=dict(snapshot.files),
    )
    state.record_run(slug, user_a, green=True, passed=1, output="green")
    saved_debrief = state.save_debrief(
        slug,
        user_a,
        root_cause="A race",
        fix_reasoning="The lock makes the mutation atomic.",
        tradeoff="The critical section reduces concurrency.",
        useful=True,
        feedback="More concurrency cases would help.",
    )
    assert saved_debrief["root_cause"] == "A race"
    assert saved_debrief["useful"] is True
    assert state.get_debrief(slug, user_a) == saved_debrief
    assert state.get_debrief(slug, user_b) is None
    marked = state.mark_spoiled(slug, user_a)
    assert marked["status"] == "solved"
    assert marked["attempts"] == 2
    assert marked["spoiled"] is True
    assert [run["green"] for run in state.list_runs(slug, 10, user_a)] == [
        True,
        False,
    ]
    state.write_file(slug, "src/answer.py", "answer = 'worse'\n", user_a)
    state.delete_file(slug, "src/extra.py", user_a)
    with pytest.raises(learner_state.RunNotFound):
        state.restore_run(slug, first_run["id"], user_b)
    restored = state.restore_run(slug, first_run["id"], user_a)
    assert restored.files == snapshot.files
    assert state.snapshot(slug, user_a).files == snapshot.files
    for number in range(9):
        state.record_run(
            slug,
            user_a,
            green=False,
            failed=1,
            workspace={"src/answer.py": f"answer = {number}\n"},
        )
    retained = state.list_runs(slug, 200, user_a)
    assert len(retained) == progress.RUN_HISTORY_LIMIT
    assert first_run["id"] not in {run["id"] for run in retained}
    assert state.get_all(user_b) == {}
    event_names = [event["event_name"] for event in state.list_product_events(user_a)]
    assert event_names.count("catalog_visit") == 2
    assert event_names.count("return_visit") == 1
    assert "path_selected" in event_names
    assert "first_run" in event_names
    assert "successful_run" in event_names
    assert "debrief_completed" in event_names
    assert "feedback_submitted" in event_names

    state.reset(slug, user_a)
    assert state.snapshot(slug, user_a).files == {}
    assert state.get_all(user_a) == {}
    assert state.list_runs(slug, 10, user_a) == []
    assert state.get_debrief(slug, user_a) is None
    assert state.get_preferences(user_a) == {"prep_path": "distributed"}


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

    with pytest.raises(learner_state.LearnerIdentityRequired):
        adapter.get_preferences(None)


def test_prep_path_is_bounded_to_the_published_curriculum() -> None:
    state = learner_state.LocalLearnerStateAdapter()

    with pytest.raises(ValueError):
        state.set_prep_path("learner", "surprise-me")
