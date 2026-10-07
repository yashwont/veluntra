"""The daily briefing: "Prepare me for today".

Assembled from the user's own data with ordinary queries and explainable rules. No
language model is involved, so it is fast, deterministic and can't invent anything.
Parts that depend on Google degrade gracefully: if Google isn't connected, that part
says so instead of failing the whole briefing.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Sequence
from datetime import datetime, time, timedelta
from typing import TypeVar
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.google.types import CalendarEvent, GoogleApi
from app.models.document import DocumentStatus
from app.models.memory import MemoryKind
from app.models.task import Task, TaskStatus
from app.proactive.detectors import sender_name
from app.proactive.priorities import rank_tasks
from app.repositories.documents import DocumentRepository
from app.repositories.memories import MemoryRepository
from app.repositories.suggestions import SuggestionRepository
from app.repositories.tasks import TaskFilters, TaskRepository
from app.schemas.briefing import (
    BriefingRead,
    ContextItem,
    DocumentBrief,
    FollowUp,
    MeetingBrief,
    PriorityItem,
    SectionStatus,
    TaskBrief,
)
from app.services.integration_service import (
    GoogleRequestError,
    IntegrationService,
    NotConnectedError,
    ReauthRequiredError,
    ScopeNotGrantedError,
)
from app.services.search_service import SearchService, SearchType

logger = logging.getLogger(__name__)
T = TypeVar("T")

MAX_PRIORITIES = 5
MAX_LIST = 8
MAX_MEETINGS = 8
CONTEXT_PER_MEETING = 3
STALE_TASK_DAYS = 7
COMMITMENT_DAYS = 30
RECENT_DOCUMENT_DAYS = 2
FOLLOW_UP_MIN_DAYS = 3
FOLLOW_UP_MAX_DAYS = 14
MAX_ACTIONS = 6


def _brief(task: Task) -> TaskBrief:
    return TaskBrief(
        id=task.id,
        title=task.title,
        priority=task.priority,
        status=task.status,
        due_date=task.due_date,
    )


async def _google_part(call: Awaitable[T], default: T) -> tuple[SectionStatus, T]:
    """Run a Google-backed step: (status, result), never raising for the usual
    'not connected' / 'expired' / 'Google is down' situations."""
    try:
        return "ok", await call
    except (NotConnectedError, ScopeNotGrantedError):
        return "not_connected", default
    except ReauthRequiredError:
        return "needs_reauth", default
    except GoogleRequestError:
        return "unavailable", default


class BriefingService:
    """The caller must already have verified the user belongs to `workspace_id`."""

    def __init__(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        google: GoogleApi | None,
        tz: ZoneInfo,
    ) -> None:
        self.session = session
        self.workspace_id = workspace_id
        self.user_id = user_id
        self.tz = tz
        self.integration = (
            IntegrationService(session, workspace_id, user_id, google) if google else None
        )

    async def build(self) -> BriefingRead:
        now = datetime.now(self.tz)
        day_start = datetime.combine(now.date(), time.min, tzinfo=self.tz)
        day_end = day_start + timedelta(days=1)
        tasks = await TaskRepository(self.session).list_open(self.workspace_id, 200)

        overdue = [t for t in tasks if t.due_date and t.due_date < now]
        due_today = [t for t in tasks if t.due_date and now <= t.due_date < day_end]
        due_tomorrow = [
            t for t in tasks if t.due_date and day_end <= t.due_date < day_end + timedelta(days=1)
        ]
        priorities = rank_tasks(tasks, now, self.tz)[:MAX_PRIORITIES]

        meetings_status, (events, conflicts) = await self._calendar(day_start, day_end)
        clashing = {event.id for pair in conflicts for event in pair}
        meetings = await self._meetings(events, clashing)

        email_status, awaiting = await self._awaiting_replies()
        follow_ups = await self._follow_ups(tasks, now, awaiting)

        documents = await self._recent_documents(now)
        pending = await SuggestionRepository(self.session).count_pending(
            self.workspace_id, self.user_id
        )

        return BriefingRead(
            date=now.date(),
            timezone=str(self.tz),
            generated_at=now,
            priorities=[
                PriorityItem(**_brief(r.task).model_dump(), reason=r.reason) for r in priorities
            ],
            overdue=[_brief(t) for t in overdue[:MAX_LIST]],
            due_today=[_brief(t) for t in due_today[:MAX_LIST]],
            due_tomorrow=[_brief(t) for t in due_tomorrow[:MAX_LIST]],
            meetings=meetings,
            meetings_status=meetings_status,
            follow_ups=follow_ups,
            follow_ups_status=email_status,
            recent_documents=documents,
            pending_suggestions=pending,
            suggested_actions=self._actions(overdue, meetings, follow_ups, pending, conflicts),
        )

    # --- Calendar ---------------------------------------------------------------------

    async def _calendar(
        self, start: datetime, end: datetime
    ) -> tuple[SectionStatus, tuple[Sequence[CalendarEvent], list[tuple[CalendarEvent, CalendarEvent]]]]:
        if self.integration is None:
            return "not_connected", ([], [])
        return await _google_part(self.integration.calendar(start, end), ([], []))

    async def _meetings(self, events: Sequence[CalendarEvent], clashing: set[str]) -> list[MeetingBrief]:
        meetings: list[MeetingBrief] = []
        for event in events[:MAX_MEETINGS]:
            context = [] if event.declined else await self._context_for(event)
            meetings.append(
                MeetingBrief(
                    id=event.id,
                    title=event.title,
                    start=event.start,
                    end=event.end,
                    all_day=event.all_day,
                    location=event.location,
                    attendees=event.attendees[:10],
                    overlaps=event.id in clashing,
                    context=context,
                )
            )
        return meetings

    async def _context_for(self, event: CalendarEvent) -> list[ContextItem]:
        """What the user already has about this meeting: their own documents, notes,
        memories and open tasks that mention its title. Event titles come from other
        people, so they are searched as plain words (search operators are not applied)."""
        if event.all_day or event.title == "(no title)":
            return []
        found = await SearchService(self.session, self.workspace_id).search_text(
            event.title,
            types={SearchType.DOCUMENT, SearchType.NOTE, SearchType.MEMORY},
            limit=CONTEXT_PER_MEETING,
        )
        context = [
            ContextItem(type=r.type.value, id=r.id, title=r.title, snippet=r.snippet)  # type: ignore[arg-type]
            for r in found
        ]
        related = await TaskRepository(self.session).search(
            self.workspace_id, TaskFilters(), query=" ".join(event.title.split()), limit=10
        )
        context += [
            ContextItem(type="task", id=t.id, title=t.title, snippet=(t.description or "")[:200])
            for t, _ in related
            if t.status in (TaskStatus.TODO, TaskStatus.IN_PROGRESS)
        ][:CONTEXT_PER_MEETING]
        return context

    # --- Follow-ups ------------------------------------------------------------------------

    async def _awaiting_replies(self):
        if self.integration is None:
            return "not_connected", []
        return await _google_part(
            self.integration.gmail_awaiting_reply(FOLLOW_UP_MIN_DAYS, FOLLOW_UP_MAX_DAYS, 5), []
        )

    async def _follow_ups(self, tasks: Sequence[Task], now: datetime, awaiting) -> list[FollowUp]:
        follow_ups = [
            FollowUp(
                kind="email",
                title=f"No reply from {sender_name(item.to.split(',')[0])}",  # first recipient
                detail=item.subject,
                days_waiting=item.days_waiting,
            )
            for item in awaiting
        ]

        stale_before = now - timedelta(days=STALE_TASK_DAYS)
        stale = sorted(
            (
                t
                for t in tasks
                if t.updated_at < stale_before
                and (t.status == TaskStatus.IN_PROGRESS or t.priority.value in ("high", "urgent"))
            ),
            key=lambda t: t.updated_at,
        )
        follow_ups += [
            FollowUp(
                kind="task",
                title=t.title,
                detail="Hasn't been touched for a while",
                days_waiting=(now - t.updated_at).days,
            )
            for t in stale[:3]
        ]

        commitments, _ = await MemoryRepository(self.session).list(
            self.workspace_id, kind=MemoryKind.COMMITMENT, limit=10, offset=0
        )
        recent = [m for m in commitments if m.updated_at >= now - timedelta(days=COMMITMENT_DAYS)]
        follow_ups += [
            FollowUp(
                kind="commitment",
                title=m.content[:200],
                detail=m.subject or "Something you committed to",
                days_waiting=(now - m.updated_at).days,
            )
            for m in recent[:3]
        ]
        return follow_ups

    # --- Documents and suggested actions -------------------------------------------------------

    async def _recent_documents(self, now: datetime) -> list[DocumentBrief]:
        documents, _ = await DocumentRepository(self.session).list(
            self.workspace_id, status=DocumentStatus.READY, limit=20, offset=0
        )
        since = now - timedelta(days=RECENT_DOCUMENT_DAYS)
        return [
            DocumentBrief(id=d.id, filename=d.filename, processed_at=d.processed_at)
            for d in documents
            if (d.processed_at or d.created_at) >= since
        ][:5]

    @staticmethod
    def _actions(
        overdue: Sequence[Task],
        meetings: Sequence[MeetingBrief],
        follow_ups: Sequence[FollowUp],
        pending: int,
        conflicts: Sequence[tuple[CalendarEvent, CalendarEvent]],
    ) -> list[str]:
        actions: list[str] = []
        if overdue:
            first = overdue[0].title
            actions.append(
                f"Clear or reschedule {len(overdue)} overdue task{'s' if len(overdue) != 1 else ''}, "
                f"starting with “{first}”."
            )
        for a, b in conflicts[:2]:
            actions.append(f"Resolve the overlap between “{a.title}” and “{b.title}”.")
        for meeting in meetings:
            docs = [c for c in meeting.context if c.type in ("document", "note")]
            if docs:
                actions.append(f"Review “{docs[0].title}” before “{meeting.title}”.")
        for item in follow_ups:
            if item.kind == "email":
                actions.append(f"Follow up: {item.title.lower()} about “{item.detail}” ({item.days_waiting} days).")
        if pending:
            actions.append(
                f"Review {pending} suggested task{'s' if pending != 1 else ''} found in your email."
            )
        return actions[:MAX_ACTIONS]
