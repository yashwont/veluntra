import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_membership
from app.db.session import get_session
from app.models.memory import MemoryKind
from app.models.workspace import WorkspaceMember
from app.schemas.common import Page
from app.schemas.memory import (
    MemoryCreate,
    MemoryRead,
    MemorySearchHit,
    MemoryUpdate,
)
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/workspaces/{workspace_id}/memories", tags=["memories"])


async def get_memory_service(
    workspace_id: uuid.UUID,
    _membership: WorkspaceMember = Depends(get_workspace_membership),
    session: AsyncSession = Depends(get_session),
) -> MemoryService:
    """Builds a MemoryService bound to the workspace, after authorizing access."""
    return MemoryService(session, workspace_id)


@router.post(
    "", response_model=MemoryRead, status_code=status.HTTP_201_CREATED, summary="Add a memory"
)
async def create_memory(
    body: MemoryCreate, service: MemoryService = Depends(get_memory_service)
) -> MemoryRead:
    """Stores something worth remembering, recorded as written by you. 409 if a
    very similar memory already exists."""
    return MemoryRead.model_validate(await service.create(body))


@router.get("", response_model=Page[MemoryRead], summary="List memories")
async def list_memories(
    kind: MemoryKind | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: MemoryService = Depends(get_memory_service),
) -> Page[MemoryRead]:
    rows, total = await service.list(kind=kind, limit=limit, offset=offset)
    return Page[MemoryRead](
        items=[MemoryRead.model_validate(m) for m in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


# Declared before "/{memory_id}" so "search" is not parsed as an id
@router.get("/search", response_model=list[MemorySearchHit], summary="Search memories")
async def search_memories(
    q: str = Query(..., min_length=1, max_length=500, description="What to look for."),
    kind: MemoryKind | None = Query(None),
    limit: int = Query(5, ge=1, le=20),
    service: MemoryService = Depends(get_memory_service),
) -> list[MemorySearchHit]:
    """Semantic search: the memories closest in meaning to the query, best first."""
    hits = await service.search(q, kind=kind, limit=limit)
    return [
        MemorySearchHit(memory=MemoryRead.model_validate(h.memory), score=h.score) for h in hits
    ]


@router.get("/{memory_id}", response_model=MemoryRead, summary="Get a memory")
async def get_memory(
    memory_id: uuid.UUID, service: MemoryService = Depends(get_memory_service)
) -> MemoryRead:
    return MemoryRead.model_validate(await service.get(memory_id))


@router.patch("/{memory_id}", response_model=MemoryRead, summary="Edit a memory")
async def update_memory(
    memory_id: uuid.UUID,
    body: MemoryUpdate,
    service: MemoryService = Depends(get_memory_service),
) -> MemoryRead:
    """Partial update. Its source stays as originally recorded."""
    return MemoryRead.model_validate(await service.update(memory_id, body))


@router.delete(
    "/{memory_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Forget a memory"
)
async def delete_memory(
    memory_id: uuid.UUID, service: MemoryService = Depends(get_memory_service)
) -> Response:
    await service.delete(memory_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
