from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, NotFoundError
from app.embeddings.factory import get_embedding_provider
from app.embeddings.types import EmbeddingProvider
from app.models.memory import Memory, MemoryKind, MemorySource
from app.repositories.memories import MemoryHit, MemoryRepository
from app.schemas.memory import MemoryCreate, MemoryUpdate

logger = logging.getLogger(__name__)

# A new memory at least this similar to an existing one is treated as a repeat
DUPLICATE_SCORE = 0.9
# Hard cap so a runaway assistant (or script) can't fill the workspace with memories
MAX_MEMORIES_PER_WORKSPACE = 1000


class MemoryNotFoundError(NotFoundError):
    code = "MEMORY_NOT_FOUND"
    message = "The requested memory does not exist."


class MemoryLimitError(AppError):
    status_code = 409
    code = "MEMORY_LIMIT_REACHED"
    message = (
        f"This workspace already holds {MAX_MEMORIES_PER_WORKSPACE} memories. "
        "Delete some before adding more."
    )


class DuplicateMemoryError(ConflictError):
    code = "MEMORY_DUPLICATE"
    message = "A very similar memory already exists."

    def __init__(self, existing: Memory) -> None:
        super().__init__()
        self.existing = existing


@dataclass(frozen=True)
class MemorySourceInfo:
    """Where a new memory came from (provenance)."""

    type: MemorySource
    id: uuid.UUID | None = None
    label: str | None = None
    confidence: float | None = None
    extraction: dict[str, Any] = field(default_factory=dict)


MANUAL_SOURCE = MemorySourceInfo(MemorySource.MANUAL, extraction={"method": "manual"})


class MemoryService:
    """Business logic for long-term memory within one workspace.

    The caller must already have verified the user belongs to `workspace_id`.
    """

    def __init__(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        *,
        embeddings: EmbeddingProvider | None = None,
    ) -> None:
        self.session = session
        self.workspace_id = workspace_id
        self.memories = MemoryRepository(session)
        self.embeddings = embeddings or get_embedding_provider()

    async def _embed(self, content: str, subject: str | None) -> list[float]:
        # The subject is part of what the memory is about, so it takes part in matching
        text = f"{subject}: {content}" if subject else content
        [vector] = await self.embeddings.embed([text])
        return vector

    async def create(
        self, data: MemoryCreate, source: MemorySourceInfo = MANUAL_SOURCE
    ) -> Memory:
        """Raises DuplicateMemoryError (carrying the existing memory) for repeats."""
        if await self.memories.count(self.workspace_id) >= MAX_MEMORIES_PER_WORKSPACE:
            raise MemoryLimitError()

        embedding = await self._embed(data.content, data.subject)
        similar = await self.memories.search(
            self.workspace_id, embedding, kind=None, limit=1, min_score=DUPLICATE_SCORE
        )
        if similar:
            raise DuplicateMemoryError(similar[0].memory)

        memory = Memory(
            workspace_id=self.workspace_id,
            kind=data.kind,
            content=data.content,
            subject=data.subject,
            source_type=source.type,
            source_id=source.id,
            source_label=source.label,
            confidence=source.confidence,
            extraction=source.extraction,
            embedding=embedding,
        )
        self.memories.add(memory)
        await self.session.commit()
        await self.session.refresh(memory)
        logger.info(
            "memory created",
            extra={
                "memory_id": str(memory.id),
                "workspace_id": str(self.workspace_id),
                "source_type": source.type.value,
            },
        )
        return memory

    async def get(self, memory_id: uuid.UUID) -> Memory:
        memory = await self.memories.get(self.workspace_id, memory_id)
        if memory is None:
            raise MemoryNotFoundError()
        return memory

    async def list(
        self, *, kind: MemoryKind | None, limit: int, offset: int
    ) -> tuple[list[Memory], int]:
        return await self.memories.list(self.workspace_id, kind=kind, limit=limit, offset=offset)

    async def update(self, memory_id: uuid.UUID, data: MemoryUpdate) -> Memory:
        memory = await self.get(memory_id)
        changes = data.model_dump(exclude_unset=True)
        for name, value in changes.items():
            setattr(memory, name, value)
        if "content" in changes or "subject" in changes:
            memory.embedding = await self._embed(memory.content, memory.subject)
        await self.session.commit()
        await self.session.refresh(memory)
        return memory

    async def delete(self, memory_id: uuid.UUID) -> None:
        memory = await self.get(memory_id)
        await self.memories.delete(memory)
        await self.session.commit()
        logger.info(
            "memory deleted",
            extra={"memory_id": str(memory_id), "workspace_id": str(self.workspace_id)},
        )

    async def search(
        self,
        query: str,
        *,
        kind: MemoryKind | None = None,
        limit: int = 5,
        min_score: float = 0.0,
    ) -> list[MemoryHit]:
        [embedding] = await self.embeddings.embed([query])
        return await self.memories.search(
            self.workspace_id, embedding, kind=kind, limit=limit, min_score=min_score
        )
