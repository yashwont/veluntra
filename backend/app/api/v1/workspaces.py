import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_workspace_membership
from app.db.session import get_session
from app.models.user import User
from app.models.workspace import WorkspaceMember
from app.repositories.workspaces import WorkspaceRepository
from app.schemas.workspace import WorkspaceRead

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("", response_model=list[WorkspaceRead], summary="List my workspaces")
async def list_workspaces(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[WorkspaceRead]:
    rows = await WorkspaceRepository(session).list_for_user(user.id)
    return [
        WorkspaceRead(id=w.id, name=w.name, role=m.role, created_at=w.created_at)
        for w, m in rows
    ]


@router.get("/{workspace_id}", response_model=WorkspaceRead, summary="Get a workspace")
async def get_workspace(
    workspace_id: uuid.UUID,
    membership: WorkspaceMember = Depends(get_workspace_membership),
    session: AsyncSession = Depends(get_session),
) -> WorkspaceRead:
    """404 if the workspace doesn't exist or the user isn't a member."""
    workspace = await WorkspaceRepository(session).get(workspace_id)
    # Membership exists, so the workspace row exists (FK guarantees it)
    assert workspace is not None
    return WorkspaceRead(
        id=workspace.id,
        name=workspace.name,
        role=membership.role,
        created_at=workspace.created_at,
    )
