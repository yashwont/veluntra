import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_membership
from app.db.session import get_session
from app.models.workspace import WorkspaceMember
from app.schemas.common import Page
from app.schemas.note import NoteCreate, NoteRead, NoteSummary, NoteUpdate, normalize_tags
from app.services.note_service import NoteService

router = APIRouter(prefix="/workspaces/{workspace_id}/notes", tags=["notes"])


async def get_note_service(
    workspace_id: uuid.UUID,
    _membership: WorkspaceMember = Depends(get_workspace_membership),
    session: AsyncSession = Depends(get_session),
) -> NoteService:
    """Builds a NoteService bound to the workspace, after authorizing access."""
    return NoteService(session, workspace_id)


@router.post(
    "", response_model=NoteRead, status_code=status.HTTP_201_CREATED, summary="Create a note"
)
async def create_note(
    body: NoteCreate, service: NoteService = Depends(get_note_service)
) -> NoteRead:
    return NoteRead.model_validate(await service.create(body))


@router.get("", response_model=Page[NoteSummary], summary="List or search notes")
async def list_notes(
    q: str | None = Query(
        None,
        min_length=1,
        max_length=200,
        description='Full-text search over title and content. Supports "quoted phrases", '
        "-excluded words and OR. Matches whole words (with stemming), not fragments. "
        "When set, results are ranked by relevance.",
    ),
    tag: list[str] | None = Query(
        None, description="Only notes having ALL given tags. Repeat the parameter."
    ),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: NoteService = Depends(get_note_service),
) -> Page[NoteSummary]:
    """Newest-updated first, or by relevance when searching. Content is returned
    as a short preview; fetch a single note for its full content."""
    try:
        tags = normalize_tags(tag) if tag else []
    except ValueError:
        # A malformed tag (empty, too long) can't match any stored note
        return Page[NoteSummary](items=[], total=0, limit=limit, offset=offset)
    rows, total = await service.list(query=q, tags=tags, limit=limit, offset=offset)
    return Page[NoteSummary](
        items=[
            NoteSummary(
                id=n.id,
                workspace_id=n.workspace_id,
                title=n.title,
                preview=preview,
                tags=n.tags,
                created_at=n.created_at,
                updated_at=n.updated_at,
            )
            for n, preview in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{note_id}", response_model=NoteRead, summary="Get a note")
async def get_note(
    note_id: uuid.UUID, service: NoteService = Depends(get_note_service)
) -> NoteRead:
    return NoteRead.model_validate(await service.get(note_id))


@router.patch("/{note_id}", response_model=NoteRead, summary="Update a note")
async def update_note(
    note_id: uuid.UUID,
    body: NoteUpdate,
    service: NoteService = Depends(get_note_service),
) -> NoteRead:
    """Partial update. `tags`, if sent, replaces the whole tag list."""
    return NoteRead.model_validate(await service.update(note_id, body))


@router.delete(
    "/{note_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a note"
)
async def delete_note(
    note_id: uuid.UUID, service: NoteService = Depends(get_note_service)
) -> Response:
    await service.delete(note_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
