import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_workspace_membership
from app.core.errors import AppError
from app.db.session import get_session
from app.integrations.google.factory import get_google_api
from app.integrations.google.types import GoogleApi
from app.models.suggestion import SuggestionStatus
from app.models.user import User
from app.models.workspace import WorkspaceMember
from app.schemas.briefing import BriefingRead
from app.schemas.suggestion import (
    ScanResult,
    SuggestionAccept,
    SuggestionAccepted,
    SuggestionRead,
)
from app.schemas.task import TaskRead
from app.services.briefing_service import BriefingService
from app.services.suggestion_service import SuggestionService

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["proactive"])


def parse_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise AppError("Unknown timezone.") from None


async def get_suggestion_service(
    workspace_id: uuid.UUID,
    _membership: WorkspaceMember = Depends(get_workspace_membership),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    google: GoogleApi = Depends(get_google_api),
) -> SuggestionService:
    return SuggestionService(session, workspace_id, user.id, google)


@router.get("/briefing", response_model=BriefingRead, summary="Prepare me for today")
async def briefing(
    workspace_id: uuid.UUID,
    timezone: str = Query("UTC", description="IANA timezone: decides what 'today' means."),
    _membership: WorkspaceMember = Depends(get_workspace_membership),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    google: GoogleApi = Depends(get_google_api),
) -> BriefingRead:
    """Your day in one place: what to do first and why, overdue and due tasks, today's
    meetings with the documents and notes you already have about them, follow-ups, and
    suggested next steps. Calendar and email parts appear once Google is connected."""
    service = BriefingService(session, workspace_id, user.id, google, parse_timezone(timezone))
    return await service.build()


@router.get(
    "/suggestions", response_model=list[SuggestionRead], summary="Suggested tasks from your email"
)
async def list_suggestions(
    status: SuggestionStatus | None = Query(SuggestionStatus.PENDING),
    service: SuggestionService = Depends(get_suggestion_service),
) -> list[SuggestionRead]:
    return [SuggestionRead.model_validate(s) for s in await service.list(status=status)]


@router.post("/suggestions/scan", response_model=ScanResult, summary="Look for tasks in my email")
async def scan_for_suggestions(
    timezone: str = Query("UTC"),
    service: SuggestionService = Depends(get_suggestion_service),
) -> ScanResult:
    """Reads your recent inbox and sent mail (needs Google connected) and proposes tasks
    for things people asked of you and for conversations awaiting a reply. Nothing
    becomes a task until you accept it."""
    created = await service.scan(parse_timezone(timezone))
    pending = await service.list(status=SuggestionStatus.PENDING)
    return ScanResult(
        created=created, pending=[SuggestionRead.model_validate(s) for s in pending]
    )


@router.post(
    "/suggestions/{suggestion_id}/accept",
    response_model=SuggestionAccepted,
    summary="Accept a suggestion (creates the task)",
)
async def accept_suggestion(
    suggestion_id: uuid.UUID,
    body: SuggestionAccept | None = Body(None),
    service: SuggestionService = Depends(get_suggestion_service),
) -> SuggestionAccepted:
    suggestion, task = await service.accept(suggestion_id, body)
    return SuggestionAccepted(
        suggestion=SuggestionRead.model_validate(suggestion), task=TaskRead.model_validate(task)
    )


@router.post(
    "/suggestions/{suggestion_id}/dismiss",
    response_model=SuggestionRead,
    summary="Dismiss a suggestion",
)
async def dismiss_suggestion(
    suggestion_id: uuid.UUID, service: SuggestionService = Depends(get_suggestion_service)
) -> SuggestionRead:
    return SuggestionRead.model_validate(await service.dismiss(suggestion_id))
