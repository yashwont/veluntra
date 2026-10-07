"""Background processing of an uploaded document: extract -> chunk -> embed -> index.

Runs outside the request that triggered it, so it opens its own database session.
Failures never propagate: they are recorded on the document (status `failed`).
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import SessionLocal
from app.documents.chunking import chunk_text
from app.documents.extract import ExtractionError, extract_text
from app.embeddings.errors import EmbeddingError
from app.embeddings.factory import get_embedding_provider
from app.embeddings.types import EmbeddingProvider
from app.models.document import Document, DocumentStatus
from app.repositories.documents import DocumentRepository
from app.storage.local import LocalFileStorage, get_file_storage

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 64


async def process_document(
    document_id: uuid.UUID,
    *,
    session_factory: async_sessionmaker[AsyncSession] = SessionLocal,
    storage: LocalFileStorage | None = None,
    embeddings: EmbeddingProvider | None = None,
) -> None:
    storage = storage or get_file_storage()
    embeddings = embeddings or get_embedding_provider()

    async with session_factory() as session:
        # Atomically claim the document: if two workers race, only one gets it
        claimed = await session.execute(
            update(Document)
            .where(Document.id == document_id, Document.status == DocumentStatus.PENDING)
            .values(status=DocumentStatus.PROCESSING, error=None)
        )
        await session.commit()
        if claimed.rowcount == 0:
            return  # deleted, already processing, or already done

        document = await session.get(Document, document_id)
        if document is None:
            return

        try:
            data = await storage.read(document.storage_key)
            text = await asyncio.to_thread(extract_text, document.filename, data)
            chunks = chunk_text(text)
            vectors: list[list[float]] = []
            for start in range(0, len(chunks), EMBED_BATCH_SIZE):
                vectors.extend(await embeddings.embed(chunks[start : start + EMBED_BATCH_SIZE]))

            await DocumentRepository(session).replace_chunks(document, chunks, vectors)
            document.status = DocumentStatus.READY
            document.chunk_count = len(chunks)
            document.processed_at = datetime.now(UTC)
            await session.commit()
            logger.info(
                "document processed",
                extra={"document_id": str(document_id), "chunks": len(chunks)},
            )
        except Exception as exc:
            await session.rollback()
            if isinstance(exc, (ExtractionError, EmbeddingError)):
                message = str(exc)  # written for users: says what to fix, no document text
            else:
                logger.exception("document processing failed", extra={"document_id": str(document_id)})
                message = "Processing failed unexpectedly. Try reprocessing the document."
            await session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(status=DocumentStatus.FAILED, error=message[:500], chunk_count=0)
            )
            await session.commit()
            logger.info(
                "document failed", extra={"document_id": str(document_id), "reason": message}
            )


async def recover_interrupted_documents() -> None:
    """Called once at startup: nothing is processing yet, so anything marked as
    pending/processing was cut off by a restart."""
    async with SessionLocal() as session:
        count = await DocumentRepository(session).mark_stuck_as_failed()
        await session.commit()
    if count:
        logger.warning("marked interrupted documents as failed", extra={"count": count})
