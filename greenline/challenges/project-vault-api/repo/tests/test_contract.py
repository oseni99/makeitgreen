"""HTTP and authorization contract for the project vault."""

import pytest
from fastapi.testclient import TestClient

from vault_api.app import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def auth(user: str, workspace: str) -> dict[str, str]:
    return {"X-User-Id": user, "X-Workspace-Id": workspace}


def test_project_member_can_list_and_read(client: TestClient) -> None:
    response = client.get(
        "/projects/project-a/documents", headers=auth("vera", "workspace-a")
    )
    assert response.status_code == 200
    assert [document["id"] for document in response.json()] == ["doc-a"]

    response = client.get(
        "/projects/project-a/documents/doc-a", headers=auth("vera", "workspace-a")
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Launch checklist"


@pytest.mark.parametrize(
    ("project_id", "document_id", "user", "workspace"),
    [
        ("project-a", "doc-secret", "alice", "workspace-a"),
        ("project-a", "doc-b", "alice", "workspace-a"),
        ("project-secret", "doc-a", "admin-a", "workspace-a"),
        ("project-secret", "doc-b", "admin-a", "workspace-a"),
        ("project-b", "doc-a", "bob", "workspace-b"),
    ],
)
def test_document_must_belong_to_project_in_url(
    client: TestClient,
    project_id: str,
    document_id: str,
    user: str,
    workspace: str,
) -> None:
    response = client.get(
        f"/projects/{project_id}/documents/{document_id}",
        headers=auth(user, workspace),
    )
    assert response.status_code == 404
    assert document_id not in response.text


def test_cross_workspace_request_is_forbidden_without_data_leak(client: TestClient) -> None:
    response = client.get(
        "/projects/project-b/documents/doc-b", headers=auth("alice", "workspace-a")
    )
    assert response.status_code == 403
    assert "Customer export" not in response.text
    assert "workspace-b/project-b" not in response.text


def test_non_member_cannot_read_project(client: TestClient) -> None:
    response = client.get(
        "/projects/project-a/documents/doc-a",
        headers=auth("charlie", "workspace-a"),
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "new_title",
    ["Viewer changed this", "Leaked edit", "Unauthorized", "Draft", "Replacement"],
)
def test_viewer_cannot_rename(client: TestClient, new_title: str) -> None:
    response = client.patch(
        "/projects/project-a/documents/doc-a",
        headers=auth("vera", "workspace-a"),
        json={"title": new_title},
    )
    assert response.status_code == 403

    unchanged = client.get(
        "/projects/project-a/documents/doc-a", headers=auth("alice", "workspace-a")
    )
    assert unchanged.json()["title"] == "Launch checklist"


@pytest.mark.parametrize("document_id", ["doc-a", "doc-secret", "doc-b"])
def test_editor_can_rename_but_cannot_delete(
    client: TestClient, document_id: str
) -> None:
    renamed = client.patch(
        "/projects/project-a/documents/doc-a",
        headers=auth("alice", "workspace-a"),
        json={"title": "Launch runbook"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Launch runbook"

    denied = client.delete(
        f"/projects/project-a/documents/{document_id}",
        headers=auth("alice", "workspace-a"),
    )
    assert denied.status_code == 403
    assert client.get(
        "/projects/project-a/documents/doc-a", headers=auth("alice", "workspace-a")
    ).status_code == 200


def test_workspace_administrator_can_delete(client: TestClient) -> None:
    response = client.delete(
        "/projects/project-a/documents/doc-a", headers=auth("admin-a", "workspace-a")
    )
    assert response.status_code == 204
    assert client.get(
        "/projects/project-a/documents/doc-a", headers=auth("admin-a", "workspace-a")
    ).status_code == 404


def test_missing_or_mismatched_credentials_are_unauthorized(client: TestClient) -> None:
    assert client.get("/projects/project-a/documents").status_code == 401
    assert client.get(
        "/projects/project-a/documents", headers=auth("alice", "workspace-b")
    ).status_code == 401
