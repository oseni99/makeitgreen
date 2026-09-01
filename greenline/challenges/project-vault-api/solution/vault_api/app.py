"""HTTP contract for the project document vault."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from pydantic import BaseModel, Field

from vault_api.store import VaultStore


USERS = {
    "alice": {"workspace_id": "workspace-a", "is_admin": False},
    "vera": {"workspace_id": "workspace-a", "is_admin": False},
    "charlie": {"workspace_id": "workspace-a", "is_admin": False},
    "admin-a": {"workspace_id": "workspace-a", "is_admin": True},
    "bob": {"workspace_id": "workspace-b", "is_admin": False},
}


@dataclass(frozen=True)
class Principal:
    user_id: str
    workspace_id: str
    is_admin: bool


class RenameDocument(BaseModel):
    title: str = Field(min_length=1, max_length=120)


def authenticated_principal(
    x_user_id: str | None = Header(default=None),
    x_workspace_id: str | None = Header(default=None),
) -> Principal:
    user = USERS.get(x_user_id or "")
    if user is None or x_workspace_id != user["workspace_id"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    return Principal(x_user_id or "", x_workspace_id, bool(user["is_admin"]))


def create_app(store: VaultStore | None = None) -> FastAPI:
    app = FastAPI(title="Project Vault API")
    vault = store or VaultStore()

    def project_role(principal: Principal, project_id: str) -> str:
        project = vault.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="project not found")
        if project["workspace_id"] != principal.workspace_id:
            raise HTTPException(status_code=403, detail="forbidden")
        if principal.is_admin:
            return "admin"
        role = project["roles"].get(principal.user_id)
        if role is None:
            raise HTTPException(status_code=403, detail="forbidden")
        return str(role)

    @app.get("/projects/{project_id}/documents")
    def list_documents(
        project_id: str, principal: Principal = Depends(authenticated_principal)
    ) -> list[dict]:
        project_role(principal, project_id)
        return vault.list_documents(principal.workspace_id, project_id)

    @app.get("/projects/{project_id}/documents/{document_id}")
    def get_document(
        project_id: str,
        document_id: str,
        principal: Principal = Depends(authenticated_principal),
    ) -> dict:
        project_role(principal, project_id)
        document = vault.get_document(principal.workspace_id, project_id, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="document not found")
        return document

    @app.patch("/projects/{project_id}/documents/{document_id}")
    def rename_document(
        project_id: str,
        document_id: str,
        body: RenameDocument,
        principal: Principal = Depends(authenticated_principal),
    ) -> dict:
        role = project_role(principal, project_id)
        if role not in {"editor", "admin"}:
            raise HTTPException(status_code=403, detail="forbidden")
        document = vault.rename_document(
            principal.workspace_id, project_id, document_id, body.title
        )
        if document is None:
            raise HTTPException(status_code=404, detail="document not found")
        return document

    @app.delete(
        "/projects/{project_id}/documents/{document_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def delete_document(
        project_id: str,
        document_id: str,
        principal: Principal = Depends(authenticated_principal),
    ) -> Response:
        role = project_role(principal, project_id)
        if role != "admin":
            raise HTTPException(status_code=403, detail="forbidden")
        if not vault.delete_document(principal.workspace_id, project_id, document_id):
            raise HTTPException(status_code=404, detail="document not found")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return app


app = create_app()
