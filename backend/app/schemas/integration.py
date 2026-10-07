import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.integration import IntegrationProvider, IntegrationStatus


class IntegrationAccountRead(BaseModel):
    """A connection, without any token."""

    id: uuid.UUID
    provider: IntegrationProvider
    account_email: str | None
    status: IntegrationStatus
    gmail: bool = Field(description="Mail access was granted.")
    calendar: bool = Field(description="Calendar access was granted.")
    drive: bool = Field(description="Drive access was granted.")
    created_at: datetime


class IntegrationsRead(BaseModel):
    demo: bool = Field(description="True when Google is simulated with canned demo data.")
    google_configured: bool = Field(
        description="False when the server has no Google client ID/secret, so connecting is impossible."
    )
    accounts: list[IntegrationAccountRead]


class ConnectResponse(BaseModel):
    authorization_url: str = Field(description="Send the browser here to grant access at Google.")


class EmailSummaryRead(BaseModel):
    id: str
    thread_id: str
    sender: str
    subject: str
    date: datetime | None
    snippet: str


class EmailRead(EmailSummaryRead):
    body: str = Field(description="Plain-text body (long messages are truncated).")


class CalendarEventRead(BaseModel):
    id: str
    title: str
    start: datetime
    end: datetime
    all_day: bool
    location: str | None
    attendees: list[str]
    link: str | None
    declined: bool


class CalendarRead(BaseModel):
    events: list[CalendarEventRead]
    conflicts: list[tuple[str, str]] = Field(
        description="Pairs of event ids that overlap in time (all-day and declined events excluded)."
    )


class DriveFileRead(BaseModel):
    id: str
    name: str
    mime_type: str
    modified_at: datetime | None
    link: str | None
    size: int | None
