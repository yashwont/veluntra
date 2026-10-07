"""Re-embed everything with the current EMBEDDING_PROVIDER.

    docker compose exec backend python -m scripts.reindex_embeddings

Run it after switching EMBEDDING_PROVIDER (for example from the built-in demo embedder to
ollama): vectors made by different models can't be compared, so old memories and
documents would otherwise be searched with the wrong yardstick. It recomputes every
memory's vector and re-processes every document (extract, chunk, embed). Safe to re-run.
"""

import asyncio
import sys

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import SessionLocal, engine
from app.embeddings.factory import get_embedding_provider
from app.embeddings.types import EmbeddingProvider
from app.models.document import Document, DocumentStatus
from app.models.memory import Memory
from app.services.document_processing import process_document
from app.services.memory_service import memory_embedding_text

BATCH = 32


async def reindex(
    provider: EmbeddingProvider | None = None,
    session_factory: async_sessionmaker[AsyncSession] = SessionLocal,
) -> tuple[int, int]:
    """Returns (memories re-embedded, documents re-processed)."""
    provider = provider or get_embedding_provider()

    async with session_factory() as session:
        memories = list((await session.execute(select(Memory))).scalars())
        for start in range(0, len(memories), BATCH):
            batch = memories[start : start + BATCH]
            vectors = await provider.embed([memory_embedding_text(m.content, m.subject) for m in batch])
            for memory, vector in zip(batch, vectors, strict=True):
                memory.embedding = vector
            await session.commit()

        document_ids = list(
            (
                await session.execute(
                    select(Document.id).where(
                        Document.status.in_([DocumentStatus.READY, DocumentStatus.FAILED])
                    )
                )
            ).scalars()
        )
        for document_id in document_ids:
            await session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(status=DocumentStatus.PENDING, error=None)
            )
            await session.commit()
            await process_document(document_id, session_factory=session_factory, embeddings=provider)

    return len(memories), len(document_ids)


async def main() -> int:
    provider = get_embedding_provider()
    print(f"Re-embedding with the '{provider.name}' provider...")
    try:
        memories, documents = await reindex(provider)
    finally:
        await engine.dispose()
    print(f"Done: {memories} memories and {documents} documents re-embedded.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
