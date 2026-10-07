from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory, MemoryKind


@dataclass(frozen=True)
class MemoryHit:
    memory: Memory
    score: float  # cosine similarity, 1.0 = identical direction


class MemoryRepository:
    """Memory data access. Every method filters on workspace_id."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, memory: Memory) -> None:
        self.session.add(memory)

    async def get(self, workspace_id: uuid.UUID, memory_id: uuid.UUID) -> Memory | None:
        result = await self.session.execute(
            select(Memory).where(Memory.id == memory_id, Memory.workspace_id == workspace_id)
        )
        return result.scalar_one_or_none()

    async def count(self, workspace_id: uuid.UUID) -> int:
        total = await self.session.scalar(
            select(func.count()).select_from(Memory).where(Memory.workspace_id == workspace_id)
        )
        return total or 0

    async def list(
        self,
        workspace_id: uuid.UUID,
        *,
        kind: MemoryKind | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Memory], int]:
        conditions = [Memory.workspace_id == workspace_id]
        if kind is not None:
            conditions.append(Memory.kind == kind)
        total = await self.session.scalar(
            select(func.count()).select_from(Memory).where(*conditions)
        )
        result = await self.session.execute(
            select(Memory)
            .where(*conditions)
            .order_by(Memory.updated_at.desc(), Memory.id)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars()), total or 0

    async def search(
        self,
        workspace_id: uuid.UUID,
        query_embedding: list[float],
        *,
        kind: MemoryKind | None,
        limit: int,
        min_score: float,
    ) -> list[MemoryHit]:
        """Nearest memories by cosine distance, best first."""
        distance = Memory.embedding.cosine_distance(query_embedding)
        conditions = [Memory.workspace_id == workspace_id, (1 - distance) >= min_score]
        if kind is not None:
            conditions.append(Memory.kind == kind)
        result = await self.session.execute(
            select(Memory, (1 - distance).label("score"))
            .where(*conditions)
            .order_by(distance)
            .limit(limit)
        )
        return [MemoryHit(memory=row[0], score=float(row[1])) for row in result.all()]

    async def delete(self, memory: Memory) -> None:
        await self.session.delete(memory)
