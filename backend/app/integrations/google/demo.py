"""A stand-in for Google that serves canned, clearly fake data (GOOGLE_PROVIDER=demo).

It lets anyone run the whole app, including the Connections page, today's meetings, email
suggestions and Drive import, without creating Google credentials. "Connecting"
redirects straight back to the app with a fixed code; nothing leaves the machine.
Dates are generated relative to today so the data always looks current.
"""

import re
from collections.abc import Sequence
from datetime import UTC, datetime, time, timedelta
from urllib.parse import urlencode

from app.core.config import get_settings
from app.integrations.google.types import (
    REQUESTED_SCOPES,
    AwaitingReply,
    CalendarEvent,
    DriveContent,
    DriveFile,
    EmailMessage,
    EmailSummary,
    GoogleApiError,
    GoogleAuthError,
    TokenSet,
)

DEMO_CODE = "demo"
DEMO_EMAIL = "demo.user@example.com"

# (id, sender, subject, snippet, body, hours ago)
_EMAILS = [
    (
        "demo-m1",
        "Ram Sharma <ram@abctraders.example>",
        "Proposal feedback",
        "Hi, thanks for the draft. Can you send me the revised pricing by Friday?",
        "Hi,\n\nThanks for the draft proposal. Can you send me the revised pricing by Friday? "
        "We would like to take it to our board next week.\n\nRam",
        5,
    ),
    (
        "demo-m2",
        "Billing <billing@cloudhost.example>",
        "Invoice 1042 is overdue",
        "Your invoice is overdue and payment is pending since last week.",
        "Dear customer,\n\nInvoice 1042 is overdue and payment is pending. Please settle it to avoid interruption.",
        20,
    ),
    (
        "demo-m3",
        "Priya Nair <priya@example.com>",
        "Quarterly revenue review - agenda",
        "Please review the attached agenda before the meeting tomorrow.",
        "Hi,\n\nPlease review the attached agenda before the quarterly revenue review.\n\nPriya",
        30,
    ),
    (
        "demo-m4",
        "Dev Weekly <newsletter@devweekly.example>",
        "Dev Weekly #212",
        "This week: a look at async Python, Postgres tips and more.",
        "This week in development...",
        40,
    ),
    (
        "demo-m5",
        "Sita Rai <sita@example.com>",
        "Photos from the trip",
        "Here are the photos from last weekend, enjoy!",
        "Here they are!",
        50,
    ),
]

_DRIVE_FILES = [
    ("demo-f1", "Q3 planning notes", "application/vnd.google-apps.document", 26, "Q3 planning notes\n\nGoals: grow revenue 15 percent, ship the mobile app, hire two engineers.\n\nRisks: delayed supplier contracts and pricing changes."),
    ("demo-f2", "ABC Traders pricing sheet", "application/vnd.google-apps.document", 70, "ABC Traders pricing sheet\n\nStandard tier 120 per unit, volume tier 95 per unit above 500 units. Payment terms net 30."),
    ("demo-f3", "Holiday photos", "image/jpeg", 200, ""),
]


def _words(query: str) -> list[str]:
    """Plain words of a Gmail-style query: operators like `in:inbox` are ignored."""
    return [w.lower() for w in query.split() if ":" not in w and not w.startswith("-")]


class DemoGoogleApi:
    # --- OAuth: "consent" is an immediate redirect back with a fixed code ----------

    def authorization_url(self, state: str) -> str:
        settings = get_settings()
        callback = f"{settings.public_backend_url}/api/v1/integrations/google/callback"
        return f"{callback}?{urlencode({'code': DEMO_CODE, 'state': state})}"

    @staticmethod
    def _tokens() -> TokenSet:
        return TokenSet(
            access_token="demo-access-token",
            refresh_token="demo-refresh-token",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            scopes=sorted(REQUESTED_SCOPES),
            email=DEMO_EMAIL,
        )

    async def exchange_code(self, code: str) -> TokenSet:
        if code != DEMO_CODE:
            raise GoogleAuthError("Unknown demo code.")
        return self._tokens()

    async def refresh(self, refresh_token: str) -> TokenSet:
        return self._tokens()

    async def revoke(self, token: str) -> None:
        return None

    # --- Gmail ------------------------------------------------------------------------

    @staticmethod
    def _summary(row: tuple) -> EmailSummary:
        id, sender, subject, snippet, _body, hours_ago = row
        return EmailSummary(
            id=id,
            thread_id=f"thread-{id}",
            sender=sender,
            subject=subject,
            date=datetime.now(UTC) - timedelta(hours=hours_ago),
            snippet=snippet,
        )

    async def gmail_search(self, access_token: str, query: str, limit: int) -> Sequence[EmailSummary]:
        words = _words(query)
        found = [
            self._summary(row)
            for row in _EMAILS
            if all(w in f"{row[1]} {row[2]} {row[3]}".lower() for w in words)
        ]
        return found[:limit]

    async def gmail_get(self, access_token: str, message_id: str) -> EmailMessage:
        for row in _EMAILS:
            if row[0] == message_id:
                s = self._summary(row)
                return EmailMessage(
                    id=s.id, thread_id=s.thread_id, sender=s.sender, subject=s.subject,
                    date=s.date, snippet=s.snippet, body=row[4],
                )
        raise GoogleApiError(404, "Google could not find that item.")

    async def gmail_awaiting_reply(
        self, access_token: str, min_days: int, max_days: int, limit: int
    ) -> Sequence[AwaitingReply]:
        now = datetime.now(UTC)
        items = [
            AwaitingReply("demo-t1", "Partnership proposal", "Anita Joshi <anita@example.com>", now - timedelta(days=5), 5),
            AwaitingReply("demo-t2", "Re: Website redesign quote", "Hari Karki <hari@example.com>", now - timedelta(days=9), 9),
        ]
        return [i for i in items if min_days <= i.days_waiting <= max_days][:limit]

    # --- Calendar -----------------------------------------------------------------------

    async def calendar_events(
        self, access_token: str, start: datetime, end: datetime
    ) -> Sequence[CalendarEvent]:
        tz = start.tzinfo or UTC
        day0 = start.date()

        def at(offset: int, hour: int, minute: int = 0) -> datetime:
            return datetime.combine(day0 + timedelta(days=offset), time(hour, minute), tzinfo=tz)

        def event(id: str, title: str, offset: int, h1: int, m1: int, h2: int, m2: int, **kw) -> CalendarEvent:
            return CalendarEvent(id=id, title=title, start=at(offset, h1, m1), end=at(offset, h2, m2), all_day=False, **kw)

        events = [
            event("demo-e1", "Sales standup", 0, 9, 0, 9, 30, attendees=["priya@example.com"]),
            event("demo-e2", "Client call - ABC Traders", 0, 10, 0, 11, 0, attendees=["ram@abctraders.example"], location="Google Meet"),
            event("demo-e3", "Proposal review", 0, 10, 30, 11, 30, attendees=["priya@example.com"]),
            event("demo-e4", "Lunch with Priya", 0, 13, 0, 14, 0, location="Cafe Nepal"),
            event("demo-e5", "Quarterly revenue review", 1, 15, 0, 16, 0, attendees=["priya@example.com", "ram@abctraders.example"]),
            event("demo-e6", "Dentist", 2, 8, 30, 9, 15),
            CalendarEvent(
                id="demo-e7", title="Team offsite", start=at(3, 0), end=at(4, 0), all_day=True, location="Pokhara",
            ),
        ]
        return [e for e in events if e.start < end and e.end > start]

    # --- Drive ----------------------------------------------------------------------------

    async def drive_search(self, access_token: str, query: str, limit: int) -> Sequence[DriveFile]:
        words = _words(query)
        now = datetime.now(UTC)
        return [
            DriveFile(id=id, name=name, mime_type=mime, modified_at=now - timedelta(hours=hours),
                      link=f"https://drive.example.com/demo/{id}")
            for id, name, mime, hours, _text in _DRIVE_FILES
            if all(w in name.lower() for w in words)
        ][:limit]

    async def drive_download(self, access_token: str, file_id: str, max_bytes: int) -> DriveContent:
        for id, name, mime, _hours, text in _DRIVE_FILES:
            if id == file_id:
                if not mime.startswith("application/vnd.google-apps.document"):
                    raise GoogleApiError(415, "That file type can't be imported. Supported: Google Docs, PDF, DOCX, TXT and MD.")
                return DriveContent(filename=f"{re.sub(r'[^A-Za-z0-9 _-]', '', name)}.txt", data=text.encode())
        raise GoogleApiError(404, "Google could not find that item.")
