from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentChunk, DocumentStatus


@dataclass(frozen=True)
class ChunkHit:
    document_id: uuid.UUID
    filename: str
    chunk_index: int
    content: str
    score: float  # cosine similarity, 1.0 = identical direction


class DocumentRepository:
    """Document data access. Every method filters on workspace_id."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, document: Document) -> None:
        self.session.add(document)

    async def get(self, workspace_id: uuid.UUID, document_id: uuid.UUID) -> Document | None:
        result = await self.session.execute(
            select(Document).where(
                Document.id == document_id, Document.workspace_id == workspace_id
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        workspace_id: uuid.UUID,
        *,
        status: DocumentStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Document], int]:
        conditions = [Document.workspace_id == workspace_id]
        if status is not None:
            conditions.append(Document.status == status)
        total = await self.session.scalar(
            select(func.count()).select_from(Document).where(*conditions)
        )
        result = await self.session.execute(
            select(Document)
            .where(*conditions)
            .order_by(Document.created_at.desc(), Document.id)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars()), total or 0

    async def delete(self, document: Document) -> None:
        await self.session.delete(document)  # chunks go with it (ON DELETE CASCADE)

    async def replace_chunks(
        self,
        document: Document,
        chunks: list[str],
        embeddings: list[list[float]],
    ) -> None:
        """Swap the document's chunks for a new set (used on every (re)processing)."""
        await self.session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document.id)
        )
        self.session.add_all(
            DocumentChunk(
                document_id=document.id,
                workspace_id=document.workspace_id,
                chunk_index=index,
                content=content,
                embedding=embedding,
            )
            for index, (content, embedding) in enumerate(zip(chunks, embeddings, strict=True))
        )

    async def search_chunks(
        self,
        workspace_id: uuid.UUID,
        query_embedding: list[float],
        *,
        limit: int,
        min_score: float,
    ) -> list[ChunkHit]:
        """Nearest chunks by cosine distance, restricted to this workspace's ready documents."""
        distance = DocumentChunk.embedding.cosine_distance(query_embedding)
        result = await self.session.execute(
            select(
                DocumentChunk.document_id,
                Document.filename,
                DocumentChunk.chunk_index,
                DocumentChunk.content,
                (1 - distance).label("score"),
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                DocumentChunk.workspace_id == workspace_id,
                Document.status == DocumentStatus.READY,
                (1 - distance) >= min_score,
            )
            .order_by(distance)
            .limit(limit)
        )
        return [
            ChunkHit(
                document_id=row.document_id,
                filename=row.filename,
                chunk_index=row.chunk_index,
                content=row.content,
                score=float(row.score),
            )
            for row in result.all()
        ]

    async def mark_stuck_as_failed(self) -> int:
        """Documents left pending/processing by a crash or restart can never finish
        on their own; flag them so users can reprocess. Not workspace-scoped: this
        is a startup maintenance task, not a user request."""
        result = await self.session.execute(
            update(Document)
            .where(Document.status.in_([DocumentStatus.PENDING, DocumentStatus.PROCESSING]))
            .values(
                status=DocumentStatus.FAILED,
                error="Processing was interrupted by a server restart. Reprocess to retry.",
            )
        )
        return result.rowcount or 0
