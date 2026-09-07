"""HTTP and authorization contract for the project vault."""

import pytest
from fastapi.testclient import TestClient

from vault_api.app import create_app


PROTECTED_DOCUMENT_DATA = {
    "doc-a": (
        "doc-a",
        "project-a",
        "workspace-a",
        "Launch checklist",
        "alice",
        "workspace-a/project-a/doc-a.md",
    ),
    "doc-secret": (
        "doc-secret",
        "project-secret",
        "workspace-a",
        "Acquisition notes",
        "admin-a",
        "workspace-a/project-secret/doc-secret.md",
    ),
    "doc-b": (
        "doc-b",
        "project-b",
        "workspace-b",
        "Customer export",
        "bob",
        "workspace-b/project-b/doc-b.csv",
    ),
}


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def auth(user: str, workspace: str) -> dict[str, str]:
    return {"X-User-Id": user, "X-Workspace-Id": workspace}


def assert_no_protected_document_data(
    response, document_id: str, current_document: dict | None = None
) -> None:
    protected_values = set(PROTECTED_DOCUMENT_DATA[document_id])
    if current_document is not None:
        protected_values.update(str(value) for value in current_document.values())
    for protected_value in protected_values:
        assert protected_value not in response.text


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
    assert_no_protected_document_data(response, document_id)


def test_cross_workspace_request_is_forbidden_without_data_leak(client: TestClient) -> None:
    response = client.get(
        "/projects/project-b/documents/doc-b", headers=auth("alice", "workspace-a")
    )
    assert response.status_code == 403
    assert_no_protected_document_data(response, "doc-b")


def test_non_member_cannot_read_project(client: TestClient) -> None:
    response = client.get(
        "/projects/project-a/documents/doc-a",
        headers=auth("charlie", "workspace-a"),
    )
    assert response.status_code == 403
    assert_no_protected_document_data(response, "doc-a")


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
    assert_no_protected_document_data(response, "doc-a")

    unchanged = client.get(
        "/projects/project-a/documents/doc-a", headers=auth("alice", "workspace-a")
    )
    assert unchanged.json()["title"] == "Launch checklist"


@pytest.mark.parametrize(
    ("document_id", "actual_project_id", "reader", "workspace"),
    [
        ("doc-a", "project-a", "alice", "workspace-a"),
        ("doc-secret", "project-secret", "admin-a", "workspace-a"),
        ("doc-b", "project-b", "bob", "workspace-b"),
    ],
)
def test_editor_can_rename_but_cannot_delete(
    client: TestClient,
    document_id: str,
    actual_project_id: str,
    reader: str,
    workspace: str,
) -> None:
    renamed = client.patch(
        "/projects/project-a/documents/doc-a",
        headers=auth("alice", "workspace-a"),
        json={"title": "Launch runbook"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Launch runbook"

    target_url = f"/projects/{actual_project_id}/documents/{document_id}"
    before = client.get(target_url, headers=auth(reader, workspace))
    assert before.status_code == 200

    denied = client.delete(
        f"/projects/project-a/documents/{document_id}",
        headers=auth("alice", "workspace-a"),
    )
    assert denied.status_code == 403
    assert_no_protected_document_data(denied, document_id, before.json())

    unchanged = client.get(target_url, headers=auth(reader, workspace))
    assert unchanged.status_code == 200
    assert unchanged.json() == before.json()


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
