from __future__ import annotations

import logging
import uuid
from datetime import datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.integrations.google.types import GoogleApi
from app.models.suggestion import Suggestion, SuggestionKind, SuggestionStatus
from app.models.task import Task, TaskPriority
from app.proactive.detectors import ActionDetector, RuleBasedDetector, clean_subject
from app.repositories.suggestions import SuggestionRepository
from app.schemas.suggestion import SuggestionAccept
from app.schemas.task import TaskCreate
from app.services.integration_service import IntegrationService

logger = logging.getLogger(__name__)

# What a scan looks at: recent mail a person might need to act on, not bulk mail
INBOX_QUERY = "in:inbox newer_than:3d -category:promotions -category:social -category:updates -category:forums"
INBOX_LIMIT = 25
# Sent mail unanswered for at least this long (and at most this long ago) is a follow-up
FOLLOW_UP_MIN_DAYS = 3
FOLLOW_UP_MAX_DAYS = 14
FOLLOW_UP_LIMIT = 10
URGENT_FOLLOW_UP_DAYS = 7


class SuggestionNotFoundError(NotFoundError):
    code = "SUGGESTION_NOT_FOUND"
    message = "The requested suggestion does not exist."


class SuggestionNotPendingError(ConflictError):
    code = "SUGGESTION_NOT_PENDING"
    message = "This suggestion has already been accepted or dismissed."


def _end_of_day(day, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, time(23, 59, 59), tzinfo=tz)


class SuggestionService:
    """Tasks Veluntra proposes from the user's email. Only the user accepting one
    creates a task. The caller must already have verified workspace membership."""

    def __init__(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        google: GoogleApi,
        detector: ActionDetector | None = None,
    ) -> None:
        self.session = session
        self.workspace_id = workspace_id
        self.user_id = user_id
        self.google = google
        self.detector = detector or RuleBasedDetector()
        self.suggestions = SuggestionRepository(session)

    async def list(self, *, status: SuggestionStatus | None, limit: int = 50) -> list[Suggestion]:
        return await self.suggestions.list(
            self.workspace_id, self.user_id, status=status, limit=limit
        )

    async def scan(self, tz: ZoneInfo) -> int:
        """Look through recent mail for things to do and people to chase.
        Returns how many new suggestions were found. Already-seen mail is skipped,
        including mail whose suggestion was dismissed."""
        integration = IntegrationService(self.session, self.workspace_id, self.user_id, self.google)
        today = datetime.now(tz).date()
        created = 0

        inbox = await integration.gmail_search(INBOX_QUERY, INBOX_LIMIT)
        own = (await integration.own_address() or "").lower()
        known = await self.suggestions.known_sources(
            self.workspace_id, self.user_id, SuggestionKind.EMAIL_ACTION, [m.id for m in inbox]
        )
        for message in inbox:
            if message.id in known or (own and own in message.sender.lower()):
                continue
            found = self.detector.detect(message, today)
            if found is None:
                continue
            created += await self._add(
                Suggestion(
                    workspace_id=self.workspace_id,
                    user_id=self.user_id,
                    kind=SuggestionKind.EMAIL_ACTION,
                    title=found.title,
                    description=found.description,
                    priority=found.priority,
                    due_date=_end_of_day(found.due_date, tz) if found.due_date else None,
                    reason=found.reason,
                    confidence=found.confidence,
                    source_type="email",
                    source_id=message.id,
                    source_label=clean_subject(message.subject)[:300],
                )
            )

        waiting = await integration.gmail_awaiting_reply(
            FOLLOW_UP_MIN_DAYS, FOLLOW_UP_MAX_DAYS, FOLLOW_UP_LIMIT
        )
        known_threads = await self.suggestions.known_sources(
            self.workspace_id,
            self.user_id,
            SuggestionKind.EMAIL_FOLLOW_UP,
            [w.thread_id for w in waiting],
        )
        for item in waiting:
            if item.thread_id in known_threads:
                continue
            subject = clean_subject(item.subject)
            created += await self._add(
                Suggestion(
                    workspace_id=self.workspace_id,
                    user_id=self.user_id,
                    kind=SuggestionKind.EMAIL_FOLLOW_UP,
                    title=f"Follow up: {subject}"[:300],
                    description=f"You wrote to {item.to or 'them'} {item.days_waiting} days ago and haven't had a reply.",
                    priority=TaskPriority.HIGH
                    if item.days_waiting >= URGENT_FOLLOW_UP_DAYS
                    else TaskPriority.MEDIUM,
                    due_date=_end_of_day(today, tz),
                    reason=f"You sent this {item.days_waiting} days ago and nobody has replied.",
                    source_type="email_thread",
                    source_id=item.thread_id,
                    source_label=subject[:300],
                )
            )

        await self.session.commit()
        logger.info(
            "mail scanned",
            extra={"workspace_id": str(self.workspace_id), "suggestions_created": created},
        )
        return created

    async def _add(self, suggestion: Suggestion) -> int:
        """Insert one suggestion; 1 if added, 0 if a concurrent scan got there first."""
        try:
            async with self.session.begin_nested():
                self.suggestions.add(suggestion)
                await self.session.flush()
        except IntegrityError:
            return 0
        return 1

    async def _pending(self, suggestion_id: uuid.UUID) -> Suggestion:
        suggestion = await self.suggestions.get(self.workspace_id, self.user_id, suggestion_id)
        if suggestion is None:
            raise SuggestionNotFoundError()
        if suggestion.status != SuggestionStatus.PENDING:
            raise SuggestionNotPendingError()
        return suggestion

    async def accept(
        self, suggestion_id: uuid.UUID, changes: SuggestionAccept | None = None
    ) -> tuple[Suggestion, Task]:
        """Turn the suggestion into a real task (optionally adjusted), in one transaction."""
        suggestion = await self._pending(suggestion_id)
        changes = changes or SuggestionAccept()
        fields = changes.model_dump(exclude_unset=True)
        data = TaskCreate(
            title=fields.get("title") or suggestion.title,
            description=suggestion.description,
            priority=fields.get("priority") or suggestion.priority,
            due_date=fields["due_date"] if "due_date" in fields else suggestion.due_date,
        )
        task = Task(
            workspace_id=self.workspace_id,
            title=data.title,
            description=data.description,
            priority=data.priority,
            due_date=data.due_date,
            source="suggestion",
        )
        self.session.add(task)
        await self.session.flush()
        suggestion.status = SuggestionStatus.ACCEPTED
        suggestion.task_id = task.id
        await self.session.commit()
        await self.session.refresh(suggestion)
        await self.session.refresh(task)
        logger.info(
            "suggestion accepted",
            extra={"suggestion_id": str(suggestion_id), "task_id": str(task.id)},
        )
        return suggestion, task

    async def dismiss(self, suggestion_id: uuid.UUID) -> Suggestion:
        suggestion = await self._pending(suggestion_id)
        suggestion.status = SuggestionStatus.DISMISSED
        await self.session.commit()
        await self.session.refresh(suggestion)
        return suggestion
