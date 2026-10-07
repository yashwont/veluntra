import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_membership
from app.db.session import get_session
from app.models.workspace import WorkspaceMember
from app.schemas.search import AppliedFilters, SearchResponse, SearchResultRead
from app.services.search_service import SearchService, SearchType

router = APIRouter(prefix="/workspaces/{workspace_id}/search", tags=["search"])


async def get_search_service(
    workspace_id: uuid.UUID,
    _membership: WorkspaceMember = Depends(get_workspace_membership),
    session: AsyncSession = Depends(get_session),
) -> SearchService:
    """Builds a SearchService bound to the workspace, after authorizing access."""
    return SearchService(session, workspace_id)


@router.get("", response_model=SearchResponse, summary="Search everything")
async def search(
    q: str = Query(
        ...,
        min_length=1,
        max_length=500,
        description="Words to look for, optionally with filters: `tag:work`, `status:todo`, "
        "`priority:high`, `is:overdue`, `kind:person`, `type:note`. A filter limits the "
        "search to the content it applies to (`priority:high` searches tasks only). "
        'Filters alone (e.g. "is:overdue") list the matches, newest first.',
    ),
    types: list[SearchType] | None = Query(
        None, description="Only these kinds of content. Repeat the parameter."
    ),
    limit: int = Query(20, ge=1, le=50),
    service: SearchService = Depends(get_search_service),
) -> SearchResponse:
    """Searches tasks, notes, documents and memories at once and returns one list,
    most relevant first. Tasks and notes match by words (full-text); documents and
    memories match by meaning (semantic)."""
    parsed, results = await service.search(q, types=set(types) if types else None, limit=limit)
    return SearchResponse(
        applied=AppliedFilters(
            text=parsed.text,
            types=sorted(parsed.candidate_types(set(types) if types else None)),
            tags=parsed.tags,
            status=parsed.status,
            priority=parsed.priority,
            overdue=parsed.overdue,
            kind=parsed.kind,
        ),
        results=[SearchResultRead.model_validate(r, from_attributes=True) for r in results],
    )
