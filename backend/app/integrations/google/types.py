"""Provider-neutral shapes for what Veluntra needs from Google, and the interface
a Google client must implement. The real client talks HTTP; tests use a fake."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

# Read-only scopes: Veluntra can look at mail, calendar and files, never change them.
SCOPE_OPENID = "openid"
SCOPE_EMAIL = "email"
SCOPE_GMAIL = "https://www.googleapis.com/auth/gmail.readonly"
SCOPE_CALENDAR = "https://www.googleapis.com/auth/calendar.readonly"
SCOPE_DRIVE = "https://www.googleapis.com/auth/drive.readonly"
REQUESTED_SCOPES = (SCOPE_OPENID, SCOPE_EMAIL, SCOPE_GMAIL, SCOPE_CALENDAR, SCOPE_DRIVE)


class GoogleError(Exception):
    """Base for failures talking to Google. Messages are safe to show to users."""


class GoogleAuthError(GoogleError):
    """Google rejected our credentials: the token expired or access was revoked."""


class GoogleApiError(GoogleError):
    def __init__(self, status: int, message: str = "Google could not complete the request.") -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str | None  # absent when Google doesn't issue a new one on refresh
    expires_at: datetime
    scopes: list[str]
    email: str | None = None


@dataclass(frozen=True)
class EmailSummary:
    id: str
    thread_id: str
    sender: str
    subject: str
    date: datetime | None
    snippet: str


@dataclass(frozen=True)
class EmailMessage(EmailSummary):
    body: str = ""  # plain text; HTML is stripped


@dataclass(frozen=True)
class CalendarEvent:
    id: str
    title: str
    start: datetime
    end: datetime
    all_day: bool
    location: str | None = None
    attendees: list[str] = field(default_factory=list)
    link: str | None = None
    declined: bool = False  # the user declined it, so it doesn't occupy their time


@dataclass(frozen=True)
class DriveFile:
    id: str
    name: str
    mime_type: str
    modified_at: datetime | None
    link: str | None
    size: int | None = None


@dataclass(frozen=True)
class DriveContent:
    """A file's content, ready to become a Veluntra document."""

    filename: str
    data: bytes


class GoogleApi(Protocol):
    # --- OAuth ---
    def authorization_url(self, state: str) -> str: ...
    async def exchange_code(self, code: str) -> TokenSet: ...
    async def refresh(self, refresh_token: str) -> TokenSet: ...
    async def revoke(self, token: str) -> None: ...

    # --- Data (all read-only) ---
    async def gmail_search(self, access_token: str, query: str, limit: int) -> Sequence[EmailSummary]: ...
    async def gmail_get(self, access_token: str, message_id: str) -> EmailMessage: ...
    async def calendar_events(
        self, access_token: str, start: datetime, end: datetime
    ) -> Sequence[CalendarEvent]: ...
    async def drive_search(self, access_token: str, query: str, limit: int) -> Sequence[DriveFile]: ...
    async def drive_download(
        self, access_token: str, file_id: str, max_bytes: int
    ) -> DriveContent: ...
