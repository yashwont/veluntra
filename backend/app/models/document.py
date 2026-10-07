import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.embeddings.types import EMBEDDING_DIMENSIONS


class DocumentStatus(enum.StrEnum):
    PENDING = "pending"  # uploaded, waiting to be processed
    PROCESSING = "processing"
    READY = "ready"  # text extracted, chunked and embedded: searchable
    FAILED = "failed"  # see Document.error


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An uploaded file. The file itself lives in file storage under `storage_key`;
    this row holds its metadata and processing state."""

    __tablename__ = "documents"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    filename: Mapped[str] = mapped_column(String(255))  # sanitized display name
    content_type: Mapped[str] = mapped_column(String(150))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(
            DocumentStatus,
            native_enum=False,
            length=20,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=DocumentStatus.PENDING,
        server_default=DocumentStatus.PENDING.value,
    )
    error: Mapped[str | None] = mapped_column(String(500), default=None)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    __table_args__ = (
        Index("ix_documents_workspace_id_created_at", "workspace_id", "created_at"),
        Index("ix_documents_workspace_id_status", "workspace_id", "status"),
    )


class DocumentChunk(UUIDPrimaryKeyMixin, Base):
    """A slice of a document's text with its embedding: the unit of semantic search."""

    __tablename__ = "document_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE")
    )
    # Denormalized so search can filter by workspace without a join
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS), deferred=True)

    __table_args__ = (
        Index("ix_document_chunks_document_id_chunk_index", "document_id", "chunk_index"),
        Index("ix_document_chunks_workspace_id", "workspace_id"),
        Index(
            "ix_document_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
