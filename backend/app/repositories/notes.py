from __future__ import annotations

import uuid

from sqlalchemy import func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.models.note import Note

PREVIEW_LENGTH = 200


class NoteRepository:
    """Note data access. Every method filters on workspace_id."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, note: Note) -> None:
        self.session.add(note)

    async def get(self, workspace_id: uuid.UUID, note_id: uuid.UUID) -> Note | None:
        result = await self.session.execute(
            select(Note).where(Note.id == note_id, Note.workspace_id == workspace_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        workspace_id: uuid.UUID,
        *,
        query: str | None,
        tags: list[str],
        limit: int,
        offset: int,
    ) -> tuple[list[tuple[Note, str]], int]:
        """Returns ([(note, preview)], total). Notes are loaded without content."""
        conditions = [Note.workspace_id == workspace_id]
        if tags:
            conditions.append(Note.tags.contains(tags))  # has ALL of these tags

        order_by = []
        if query:
            # websearch_to_tsquery accepts raw user input ("quoted phrase", -excluded,
            # or) and never raises a syntax error
            ts_query = func.websearch_to_tsquery(literal_column("'english'"), query)
            conditions.append(Note.search_vector.op("@@")(ts_query))
            order_by.append(func.ts_rank(Note.search_vector, ts_query).desc())
        order_by += [Note.updated_at.desc(), Note.id]

        total = await self.session.scalar(
            select(func.count()).select_from(Note).where(*conditions)
        )
        result = await self.session.execute(
            select(Note, func.left(Note.content, PREVIEW_LENGTH).label("preview"))
            .options(defer(Note.content))
            .where(*conditions)
            .order_by(*order_by)
            .limit(limit)
            .offset(offset)
        )
        return [(row[0], row[1]) for row in result.all()], total or 0

    async def delete(self, note: Note) -> None:
        await self.session.delete(note)

    async def search(
        self,
        workspace_id: uuid.UUID,
        *,
        query: str | None,
        tags: list[str],
        limit: int,
    ) -> list[tuple[Note, str, float | None]]:
        """(note, preview, rank): best match first with a rank, or newest first
        with rank None when there is no text query. Notes are loaded without content."""
        conditions = [Note.workspace_id == workspace_id]
        if tags:
            conditions.append(Note.tags.contains(tags))
        preview = func.left(Note.content, PREVIEW_LENGTH).label("preview")
        if query:
            ts_query = func.websearch_to_tsquery(literal_column("'english'"), query)
            conditions.append(Note.search_vector.op("@@")(ts_query))
            rank = func.ts_rank(Note.search_vector, ts_query)
            result = await self.session.execute(
                select(Note, preview, rank)
                .options(defer(Note.content))
                .where(*conditions)
                .order_by(rank.desc(), Note.id)
                .limit(limit)
            )
            return [(row[0], row[1], float(row[2])) for row in result.all()]
        result = await self.session.execute(
            select(Note, preview)
            .options(defer(Note.content))
            .where(*conditions)
            .order_by(Note.updated_at.desc(), Note.id)
            .limit(limit)
        )
        return [(row[0], row[1], None) for row in result.all()]
