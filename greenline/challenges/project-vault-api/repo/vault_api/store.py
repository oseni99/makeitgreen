"""In-memory project and document repository."""
from __future__ import annotations

from copy import deepcopy


class VaultStore:
    def __init__(self) -> None:
        self.projects = {
            "project-a": {
                "id": "project-a",
                "workspace_id": "workspace-a",
                "roles": {"alice": "editor", "vera": "viewer"},
            },
            "project-secret": {
                "id": "project-secret",
                "workspace_id": "workspace-a",
                "roles": {"admin-a": "admin"},
            },
            "project-b": {
                "id": "project-b",
                "workspace_id": "workspace-b",
                "roles": {"bob": "editor"},
            },
        }
        self.documents = {
            "doc-a": {
                "id": "doc-a",
                "project_id": "project-a",
                "workspace_id": "workspace-a",
                "title": "Launch checklist",
                "owner_id": "alice",
                "storage_key": "workspace-a/project-a/doc-a.md",
            },
            "doc-secret": {
                "id": "doc-secret",
                "project_id": "project-secret",
                "workspace_id": "workspace-a",
                "title": "Acquisition notes",
                "owner_id": "admin-a",
                "storage_key": "workspace-a/project-secret/doc-secret.md",
            },
            "doc-b": {
                "id": "doc-b",
                "project_id": "project-b",
                "workspace_id": "workspace-b",
                "title": "Customer export",
                "owner_id": "bob",
                "storage_key": "workspace-b/project-b/doc-b.csv",
            },
        }

    def get_project(self, project_id: str) -> dict | None:
        project = self.projects.get(project_id)
        return deepcopy(project) if project is not None else None

    def list_documents(self, workspace_id: str, project_id: str) -> list[dict]:
        return [
            self._public(document)
            for document in sorted(self.documents.values(), key=lambda item: item["id"])
            if document["workspace_id"] == workspace_id
            and document["project_id"] == project_id
        ]

    def get_document(
        self, workspace_id: str, project_id: str, document_id: str
    ) -> dict | None:
        # BUG: the URL scope is ignored once a globally valid document ID is known.
        document = self.documents.get(document_id)
        return self._public(document) if document is not None else None

    def rename_document(
        self, workspace_id: str, project_id: str, document_id: str, title: str
    ) -> dict | None:
        document = self.documents.get(document_id)
        if document is None:
            return None
        document["title"] = title
        return self._public(document)

    def delete_document(
        self, workspace_id: str, project_id: str, document_id: str
    ) -> bool:
        if document_id not in self.documents:
            return False
        del self.documents[document_id]
        return True

    @staticmethod
    def _public(document: dict) -> dict:
        return {
            "id": document["id"],
            "project_id": document["project_id"],
            "title": document["title"],
            "owner_id": document["owner_id"],
            "storage_key": document["storage_key"],
        }
