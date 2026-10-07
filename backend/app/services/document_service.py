from __future__ import annotations

import hashlib
import logging
import re
import uuid
from pathlib import Path, PurePath

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.documents.extract import detect_type
from app.embeddings.factory import get_embedding_provider
from app.embeddings.types import EmbeddingProvider
from app.models.document import Document, DocumentStatus
from app.repositories.documents import ChunkHit, DocumentRepository
from app.storage.local import LocalFileStorage, get_file_storage

logger = logging.getLogger(__name__)

MAX_FILENAME_LENGTH = 255
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class DocumentNotFoundError(NotFoundError):
    code = "DOCUMENT_NOT_FOUND"
    message = "The requested document does not exist."


class InvalidUploadError(AppError):
    status_code = 422
    code = "INVALID_UPLOAD"
    message = "The uploaded file is not valid."


class UploadTooLargeError(AppError):
    status_code = 413
    code = "UPLOAD_TOO_LARGE"
    message = "The uploaded file is too large."


class DocumentBusyError(ConflictError):
    code = "DOCUMENT_BUSY"
    message = "The document is still being processed."


def sanitize_filename(raw: str | None) -> str:
    """A safe display name: no directories, no control characters, bounded length.

    Only ever used for display and the download header, never to build a path.
    """
    name = PurePath((raw or "").replace("\\", "/")).name
    name = _CONTROL_CHARS.sub("", name).strip().strip(".")
    if not name:
        return "document"
    if len(name) > MAX_FILENAME_LENGTH:
        suffix = Path(name).suffix[:20]
        name = name[: MAX_FILENAME_LENGTH - len(suffix)] + suffix
    return name


class DocumentService:
    """Business logic for documents within one workspace.

    The caller must already have verified the user belongs to `workspace_id`.
    """

    def __init__(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        *,
        storage: LocalFileStorage | None = None,
        embeddings: EmbeddingProvider | None = None,
    ) -> None:
        self.session = session
        self.workspace_id = workspace_id
        self.documents = DocumentRepository(session)
        self.storage = storage or get_file_storage()
        self.embeddings = embeddings or get_embedding_provider()

    async def upload(
        self, *, filename: str | None, data: bytes, user_id: uuid.UUID
    ) -> Document:
        """Validate and store the file, and create a `pending` document.
        Processing is started separately (see document_processing)."""
        if len(data) > get_settings().max_upload_bytes:
            raise UploadTooLargeError()
        if not data:
            raise InvalidUploadError("The uploaded file is empty.")

        safe_name = sanitize_filename(filename)
        try:
            content_type = detect_type(safe_name, data)
        except AppError:
            raise
        except Exception as exc:  # ExtractionError subclasses carry user-safe text
            raise InvalidUploadError(str(exc)) from exc

        key = self.storage.new_key(self.workspace_id)
        await self.storage.save(key, data)
        document = Document(
            workspace_id=self.workspace_id,
            uploaded_by_id=user_id,
            filename=safe_name,
            content_type=content_type,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            storage_key=key,
        )
        self.documents.add(document)
        try:
            await self.session.commit()
        except Exception:
            await self.storage.delete(key)  # don't leave an orphaned file behind
            raise
        await self.session.refresh(document)
        logger.info(
            "document uploaded",
            extra={
                "document_id": str(document.id),
                "workspace_id": str(self.workspace_id),
                "size_bytes": document.size_bytes,
            },
        )
        return document

    async def get(self, document_id: uuid.UUID) -> Document:
        document = await self.documents.get(self.workspace_id, document_id)
        if document is None:
            raise DocumentNotFoundError()
        return document

    async def list(
        self, *, status: DocumentStatus | None, limit: int, offset: int
    ) -> tuple[list[Document], int]:
        return await self.documents.list(
            self.workspace_id, status=status, limit=limit, offset=offset
        )

    async def delete(self, document_id: uuid.UUID) -> None:
        document = await self.get(document_id)
        key = document.storage_key
        await self.documents.delete(document)
        await self.session.commit()
        # After the commit: if this fails we leak a file, never a row pointing at nothing
        try:
            await self.storage.delete(key)
        except OSError:
            logger.exception("could not delete stored file", extra={"storage_key": key})
        logger.info(
            "document deleted",
            extra={"document_id": str(document_id), "workspace_id": str(self.workspace_id)},
        )

    async def reset_for_reprocessing(self, document_id: uuid.UUID) -> Document:
        """Put a finished or failed document back to `pending`."""
        document = await self.get(document_id)
        if document.status in (DocumentStatus.PENDING, DocumentStatus.PROCESSING):
            raise DocumentBusyError()
        document.status = DocumentStatus.PENDING
        document.error = None
        await self.session.commit()
        await self.session.refresh(document)
        return document

    async def search(
        self, query: str, *, limit: int, min_score: float = 0.0
    ) -> list[ChunkHit]:
        """Semantic search over the workspace's processed documents."""
        [embedding] = await self.embeddings.embed([query])
        return await self.documents.search_chunks(
            self.workspace_id, embedding, limit=limit, min_score=min_score
        )
