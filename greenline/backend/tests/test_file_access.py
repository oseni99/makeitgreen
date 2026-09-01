import json

import pytest
from fastapi.testclient import TestClient

import challenges
from app import app


@pytest.fixture
def isolated_backend(tmp_path, monkeypatch):
    challenges_dir = tmp_path / "challenges"
    workspaces_dir = tmp_path / "data" / "workspaces"
    challenge_dir = challenges_dir / "sample"
    repo_dir = challenge_dir / "repo"

    (repo_dir / "tests").mkdir(parents=True)
    (repo_dir / "src" / "nested").mkdir(parents=True)
    (repo_dir / "tests" / "test_guard.py").write_text("original test\n")
    (repo_dir / "conftest.py").write_text("original pytest hooks\n")
    (repo_dir / "src" / "conftest.py").write_text("nested pytest hooks\n")
    for config_name in challenges.PYTEST_CONFIG_FILES:
        (repo_dir / config_name).write_text("original pytest config\n")
    (repo_dir / "src" / "nested" / "service.py").write_text("original source\n")
    (challenge_dir / "challenge.json").write_text(
        json.dumps(
            {
                "title": "Sample",
                "readonly": ["tests/"],
                "creatable": ["src/", "orders/"],
            }
        )
    )

    monkeypatch.setattr(challenges, "CHALLENGES_DIR", challenges_dir)
    monkeypatch.setattr(challenges, "WORKSPACES_DIR", workspaces_dir)

    return repo_dir, workspaces_dir


def test_encoded_internal_traversal_cannot_overwrite_readonly_file(isolated_backend):
    repo_dir, workspaces_dir = isolated_backend
    client = TestClient(app)

    response = client.put(
        "/api/challenges/sample/files/src%2F..%2Ftests%2Ftest_guard.py",
        json={"content": "overwritten\n"},
    )

    assert response.status_code == 403
    assert (repo_dir / "tests" / "test_guard.py").read_text() == "original test\n"
    assert not (workspaces_dir / "sample" / "tests" / "test_guard.py").exists()


def test_nested_editable_file_can_be_saved(isolated_backend):
    _, workspaces_dir = isolated_backend
    client = TestClient(app)

    response = client.put(
        "/api/challenges/sample/files/src/nested/service.py",
        json={"content": "updated source\n"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert (
        workspaces_dir / "sample" / "src" / "nested" / "service.py"
    ).read_text() == "updated source\n"


@pytest.mark.parametrize(
    "path",
    ["conftest.py", "src/conftest.py", *sorted(challenges.PYTEST_CONFIG_FILES)],
)
def test_pytest_control_files_cannot_be_edited(isolated_backend, path):
    repo_dir, workspaces_dir = isolated_backend
    client = TestClient(app)

    response = client.put(
        f"/api/challenges/sample/files/{path}",
        json={"content": "def pytest_sessionfinish(session):\n    session.exitstatus = 0\n"},
    )

    assert response.status_code == 403
    assert not (workspaces_dir / "sample" / path).exists()
    assert "pytest_sessionfinish" not in (repo_dir / path).read_text()


def test_traversal_outside_repo_is_rejected(isolated_backend):
    _, workspaces_dir = isolated_backend
    client = TestClient(app)

    response = client.put(
        "/api/challenges/sample/files/%2E%2E%2Foutside.py",
        json={"content": "escaped\n"},
    )

    assert response.status_code == 400
    assert not (workspaces_dir / "outside.py").exists()


def test_create_file_under_creatable_prefix(isolated_backend):
    _, workspaces_dir = isolated_backend
    client = TestClient(app)

    response = client.post(
        "/api/challenges/sample/files/orders/handler.py",
        json={"content": "def handle():\n    return 1\n"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "path": "orders/handler.py",
        "new": True,
    }
    assert (
        workspaces_dir / "sample" / "orders" / "handler.py"
    ).read_text() == "def handle():\n    return 1\n"

    tree = client.get("/api/challenges/sample").json()["files"]
    entry = next(f for f in tree if f["path"] == "orders/handler.py")
    assert entry["new"] is True
    assert entry["readonly"] is False
    original = next(f for f in tree if f["path"] == "src/nested/service.py")
    assert original["new"] is False


def test_create_file_outside_creatable_prefix_is_rejected(isolated_backend):
    _, workspaces_dir = isolated_backend
    client = TestClient(app)

    response = client.post(
        "/api/challenges/sample/files/lib/helper.py",
        json={"content": "x = 1\n"},
    )

    assert response.status_code == 403
    assert not (workspaces_dir / "sample" / "lib" / "helper.py").exists()


def test_create_file_refused_without_creatable_whitelist(isolated_backend):
    repo_dir, workspaces_dir = isolated_backend
    (repo_dir.parent / "challenge.json").write_text(
        json.dumps({"title": "Sample", "readonly": ["tests/"]})
    )
    client = TestClient(app)

    response = client.post(
        "/api/challenges/sample/files/src/extra.py",
        json={"content": "x = 1\n"},
    )

    assert response.status_code == 403
    assert not (workspaces_dir / "sample" / "src" / "extra.py").exists()


def test_create_under_readonly_prefix_is_rejected(isolated_backend):
    repo_dir, workspaces_dir = isolated_backend
    client = TestClient(app)

    response = client.post(
        "/api/challenges/sample/files/tests/test_new.py",
        json={"content": "def test_cheat():\n    assert True\n"},
    )

    assert response.status_code == 403
    assert not (workspaces_dir / "sample" / "tests" / "test_new.py").exists()
    assert not (repo_dir / "tests" / "test_new.py").exists()


@pytest.mark.parametrize(
    "path",
    ["conftest.py", "src/conftest.py", *sorted(challenges.PYTEST_CONFIG_FILES)],
)
def test_create_pytest_control_files_is_rejected(isolated_backend, path):
    _, workspaces_dir = isolated_backend
    client = TestClient(app)

    response = client.post(
        f"/api/challenges/sample/files/{path}",
        json={"content": "def pytest_sessionfinish(session):\n    session.exitstatus = 0\n"},
    )

    assert response.status_code == 403
    assert not (workspaces_dir / "sample" / path).exists()


def test_create_traversal_outside_repo_is_rejected(isolated_backend):
    _, workspaces_dir = isolated_backend
    client = TestClient(app)

    response = client.post(
        "/api/challenges/sample/files/%2E%2E%2Foutside.py",
        json={"content": "escaped\n"},
    )

    assert response.status_code == 400
    assert not (workspaces_dir / "outside.py").exists()


def test_create_encoded_traversal_cannot_land_in_tests(isolated_backend):
    repo_dir, workspaces_dir = isolated_backend
    client = TestClient(app)

    response = client.post(
        "/api/challenges/sample/files/src%2F..%2Ftests%2Fplanted.py",
        json={"content": "planted\n"},
    )

    assert response.status_code == 403
    assert not (workspaces_dir / "sample" / "tests" / "planted.py").exists()
    assert not (repo_dir / "tests" / "planted.py").exists()


def test_put_still_cannot_create_missing_file(isolated_backend):
    _, workspaces_dir = isolated_backend
    client = TestClient(app)

    response = client.put(
        "/api/challenges/sample/files/orders/missing.py",
        json={"content": "nope\n"},
    )

    assert response.status_code == 404
    assert not (workspaces_dir / "sample" / "orders" / "missing.py").exists()


def test_put_can_update_created_workspace_file(isolated_backend):
    _, workspaces_dir = isolated_backend
    client = TestClient(app)

    created = client.post(
        "/api/challenges/sample/files/src/extra.py",
        json={"content": "v1\n"},
    )
    assert created.status_code == 200

    updated = client.put(
        "/api/challenges/sample/files/src/extra.py",
        json={"content": "v2\n"},
    )
    assert updated.status_code == 200
    assert (workspaces_dir / "sample" / "src" / "extra.py").read_text() == "v2\n"


def test_file_tree_merges_workspace_only_files(isolated_backend):
    challenges.create_file("sample", "orders/new_mod.py", "pass\n")
    tree = challenges.file_tree("sample")
    by_path = {f["path"]: f for f in tree}

    assert by_path["orders/new_mod.py"]["new"] is True
    assert by_path["orders/new_mod.py"]["edited"] is True
    assert by_path["src/nested/service.py"]["new"] is False
    assert by_path["tests/test_guard.py"]["new"] is False


def test_delete_workspace_only_file(isolated_backend):
    _, workspaces_dir = isolated_backend
    client = TestClient(app)
    client.post(
        "/api/challenges/sample/files/orders/tmp.py",
        json={"content": "pass\n"},
    )

    response = client.delete("/api/challenges/sample/files/orders/tmp.py")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert not (workspaces_dir / "sample" / "orders" / "tmp.py").exists()
    tree = client.get("/api/challenges/sample").json()["files"]
    assert all(f["path"] != "orders/tmp.py" for f in tree)


def test_delete_original_repo_file_is_rejected(isolated_backend):
    repo_dir, workspaces_dir = isolated_backend
    client = TestClient(app)

    response = client.delete("/api/challenges/sample/files/src/nested/service.py")

    assert response.status_code == 403
    assert (repo_dir / "src" / "nested" / "service.py").read_text() == "original source\n"
    assert not (workspaces_dir / "sample" / "src" / "nested" / "service.py").exists()


def test_delete_workspace_overlay_of_original_is_rejected(isolated_backend):
    _, workspaces_dir = isolated_backend
    client = TestClient(app)
    client.put(
        "/api/challenges/sample/files/src/nested/service.py",
        json={"content": "edited overlay\n"},
    )

    response = client.delete("/api/challenges/sample/files/src/nested/service.py")

    assert response.status_code == 403
    assert (
        workspaces_dir / "sample" / "src" / "nested" / "service.py"
    ).read_text() == "edited overlay\n"


def test_delete_traversal_outside_repo_is_rejected(isolated_backend):
    _, workspaces_dir = isolated_backend
    workspaces_dir.mkdir(parents=True, exist_ok=True)
    (workspaces_dir / "outside.py").write_text("keep\n")
    client = TestClient(app)

    response = client.delete("/api/challenges/sample/files/%2E%2E%2Foutside.py")

    assert response.status_code == 400
    assert (workspaces_dir / "outside.py").read_text() == "keep\n"


def test_create_existing_repo_file_conflicts(isolated_backend):
    client = TestClient(app)

    response = client.post(
        "/api/challenges/sample/files/src/nested/service.py",
        json={"content": "duplicate\n"},
    )

    assert response.status_code == 409


def test_delete_missing_workspace_file_returns_404(isolated_backend):
    client = TestClient(app)

    response = client.delete("/api/challenges/sample/files/orders/ghost.py")

    assert response.status_code == 404


def test_search_finds_matches_and_prefers_workspace_overlay(isolated_backend):
    repo_dir, workspaces_dir = isolated_backend
    (repo_dir / "src" / "nested" / "service.py").write_text(
        "def hello():\n    return 'alpha-token'\n"
    )
    ws_file = workspaces_dir / "sample" / "src" / "nested" / "service.py"
    ws_file.parent.mkdir(parents=True)
    ws_file.write_text("def hello():\n    return 'beta-token'\n")
    client = TestClient(app)

    response = client.get("/api/challenges/sample/search", params={"q": "beta-token"})
    assert response.status_code == 200
    hits = response.json()["hits"]
    assert any(h["path"] == "src/nested/service.py" and h["line"] == 2 for h in hits)

    # Overlay wins: original alpha-token should not appear once overwritten.
    response = client.get("/api/challenges/sample/search", params={"q": "alpha-token"})
    assert response.json()["hits"] == []


def test_search_empty_query_returns_no_hits(isolated_backend):
    client = TestClient(app)
    response = client.get("/api/challenges/sample/search", params={"q": "   "})
    assert response.status_code == 200
    assert response.json()["hits"] == []
