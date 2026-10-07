import logging
import uuid
from dataclasses import asdict
from datetime import datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, BackgroundTasks, Depends, Path, Query, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_workspace_membership
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import get_session
from app.integrations.google.factory import get_google_api
from app.integrations.google.types import SCOPE_CALENDAR, SCOPE_DRIVE, SCOPE_GMAIL, GoogleApi
from app.models.integration import IntegrationAccount
from app.models.user import User
from app.models.workspace import WorkspaceMember
from app.schemas.document import DocumentRead
from app.schemas.integration import (
    CalendarEventRead,
    CalendarRead,
    ConnectResponse,
    DriveFileRead,
    EmailRead,
    EmailSummaryRead,
    IntegrationAccountRead,
    IntegrationsRead,
)
from app.services.document_processing import process_document
from app.services.integration_service import IntegrationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces/{workspace_id}/integrations", tags=["integrations"])
# Public: Google sends the user's browser here, so there is no Authorization header
callback_router = APIRouter(prefix="/integrations/google", tags=["integrations"])

# Ids go straight into Google URLs, so only their real alphabet is accepted
GoogleId = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,200}$")]


async def get_integration_service(
    workspace_id: uuid.UUID,
    _membership: WorkspaceMember = Depends(get_workspace_membership),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    google: GoogleApi = Depends(get_google_api),
) -> IntegrationService:
    return IntegrationService(session, workspace_id, user.id, google)


def _account_read(account: IntegrationAccount) -> IntegrationAccountRead:
    return IntegrationAccountRead(
        id=account.id,
        provider=account.provider,
        account_email=account.account_email,
        status=account.status,
        gmail=SCOPE_GMAIL in account.scopes,
        calendar=SCOPE_CALENDAR in account.scopes,
        drive=SCOPE_DRIVE in account.scopes,
        created_at=account.created_at,
    )


# --- Connections ----------------------------------------------------------------------


@router.get("", response_model=IntegrationsRead, summary="My connected accounts")
async def list_integrations(
    service: IntegrationService = Depends(get_integration_service),
) -> IntegrationsRead:
    accounts = await service.list_accounts()
    return IntegrationsRead(
        demo=get_settings().google_demo,
        google_configured=get_settings().google_configured,
        accounts=[_account_read(a) for a in accounts],
    )


@router.post("/google/connect", response_model=ConnectResponse, summary="Start connecting Google")
async def connect_google(
    service: IntegrationService = Depends(get_integration_service),
) -> ConnectResponse:
    """Returns the Google consent URL. Veluntra asks for read-only access to Gmail,
    Calendar and Drive; it can never send, create or change anything there."""
    return ConnectResponse(authorization_url=service.begin_connect())


@router.delete(
    "/{account_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Disconnect an account"
)
async def disconnect(
    account_id: uuid.UUID, service: IntegrationService = Depends(get_integration_service)
) -> Response:
    """Revokes the access at Google and deletes the stored tokens."""
    await service.disconnect(account_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@callback_router.get("/callback", include_in_schema=False)
async def google_callback(
    code: str | None = Query(None, max_length=2048),
    state: str | None = Query(None, max_length=2048),
    error: str | None = Query(None, max_length=200),
    session: AsyncSession = Depends(get_session),
    google: GoogleApi = Depends(get_google_api),
) -> RedirectResponse:
    """Where Google sends the browser back. Always ends in a redirect to the app, with
    the outcome in the address (never tokens, never details)."""
    base = f"{get_settings().frontend_url}/integrations"
    if error or not code or not state:
        return RedirectResponse(f"{base}?google={'denied' if error == 'access_denied' else 'error'}")
    try:
        await IntegrationService.complete_connect(session, google, code=code, state=state)
    except AppError as exc:
        logger.info("google connect failed", extra={"code": exc.code})
        return RedirectResponse(f"{base}?google=error&reason={exc.code}")
    return RedirectResponse(f"{base}?google=connected")


# --- Reading Google data ------------------------------------------------------------------


@router.get(
    "/google/gmail/messages", response_model=list[EmailSummaryRead], summary="Search my email"
)
async def search_email(
    q: str = Query("", max_length=500, description="Gmail search syntax, e.g. from:ram newer_than:7d"),
    limit: int = Query(10, ge=1, le=25),
    service: IntegrationService = Depends(get_integration_service),
) -> list[EmailSummaryRead]:
    return [
        EmailSummaryRead(**asdict(m)) for m in await service.gmail_search(q, limit)
    ]


@router.get(
    "/google/gmail/messages/{message_id}", response_model=EmailRead, summary="Read one email"
)
async def read_email(
    message_id: GoogleId, service: IntegrationService = Depends(get_integration_service)
) -> EmailRead:
    return EmailRead(**asdict(await service.gmail_read(message_id)))


@router.get("/google/calendar/events", response_model=CalendarRead, summary="My upcoming schedule")
async def calendar_events(
    days: int = Query(7, ge=1, le=31),
    timezone: str = Query("UTC", description="IANA timezone: the window starts at midnight today there."),
    service: IntegrationService = Depends(get_integration_service),
) -> CalendarRead:
    """Events from the start of today for `days` days, plus which of them overlap."""
    try:
        tz = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise AppError("Unknown timezone.") from None
    start = datetime.combine(datetime.now(tz).date(), time.min, tzinfo=tz)
    events, conflicts = await service.calendar(start, start + timedelta(days=days))
    return CalendarRead(
        events=[CalendarEventRead(**asdict(e)) for e in events],
        conflicts=[(a.id, b.id) for a, b in conflicts],
    )


@router.get("/google/drive/files", response_model=list[DriveFileRead], summary="Search my Drive")
async def search_drive(
    q: str = Query("", max_length=300, description="Words to find in file names and contents."),
    limit: int = Query(10, ge=1, le=25),
    service: IntegrationService = Depends(get_integration_service),
) -> list[DriveFileRead]:
    return [
        DriveFileRead(
            id=f.id, name=f.name, mime_type=f.mime_type, modified_at=f.modified_at,
            link=f.link, size=f.size,
        )
        for f in await service.drive_search(q, limit)
    ]


@router.post(
    "/google/drive/files/{file_id}/import",
    response_model=DocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Import a Drive file as a document",
)
async def import_drive_file(
    file_id: GoogleId,
    background: BackgroundTasks,
    service: IntegrationService = Depends(get_integration_service),
) -> DocumentRead:
    """Copies the file into your documents (Google Docs, PDF, DOCX, TXT or MD) so it
    is extracted, indexed and searchable like an upload. The original is untouched."""
    document = await service.drive_import(file_id)
    background.add_task(process_document, document.id)
    return DocumentRead.model_validate(document)
