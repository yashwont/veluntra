from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.suggestion import Suggestion, SuggestionKind, SuggestionStatus


class SuggestionRepository:
    """Suggestions are personal: every method filters on workspace and user."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, suggestion: Suggestion) -> None:
        self.session.add(suggestion)

    async def get(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, suggestion_id: uuid.UUID
    ) -> Suggestion | None:
        result = await self.session.execute(
            select(Suggestion).where(
                Suggestion.id == suggestion_id,
                Suggestion.workspace_id == workspace_id,
                Suggestion.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        status: SuggestionStatus | None,
        limit: int,
    ) -> list[Suggestion]:
        conditions = [Suggestion.workspace_id == workspace_id, Suggestion.user_id == user_id]
        if status is not None:
            conditions.append(Suggestion.status == status)
        result = await self.session.execute(
            select(Suggestion)
            .where(*conditions)
            .order_by(Suggestion.created_at.desc(), Suggestion.id)
            .limit(limit)
        )
        return list(result.scalars())

    async def count_pending(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> int:
        total = await self.session.scalar(
            select(func.count())
            .select_from(Suggestion)
            .where(
                Suggestion.workspace_id == workspace_id,
                Suggestion.user_id == user_id,
                Suggestion.status == SuggestionStatus.PENDING,
            )
        )
        return total or 0

    async def known_sources(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        kind: SuggestionKind,
        source_ids: list[str],
    ) -> set[str]:
        """Which of these sources already have a suggestion (in any status)."""
        if not source_ids:
            return set()
        result = await self.session.execute(
            select(Suggestion.source_id).where(
                Suggestion.workspace_id == workspace_id,
                Suggestion.user_id == user_id,
                Suggestion.kind == kind,
                Suggestion.source_id.in_(source_ids),
            )
        )
        return set(result.scalars())
