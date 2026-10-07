import enum
import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Enum, Float, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.embeddings.types import EMBEDDING_DIMENSIONS


class MemoryKind(enum.StrEnum):
    PERSON = "person"
    PROJECT = "project"
    PREFERENCE = "preference"
    COMMITMENT = "commitment"
    EVENT = "event"
    DECISION = "decision"
    FACT = "fact"  # anything durable that fits no other kind


class MemorySource(enum.StrEnum):
    CONVERSATION = "conversation"
    NOTE = "note"
    DOCUMENT = "document"
    MANUAL = "manual"


def _enum_column(enum_cls: type[enum.StrEnum]) -> Enum:
    return Enum(
        enum_cls,
        native_enum=False,
        length=20,
        values_callable=lambda e: [m.value for m in e],
    )


class Memory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One durable thing worth remembering about the user, with where it came from.

    Provenance is a snapshot, not a foreign key: the source (a conversation, note
    or document) may be deleted later, and the memory should still say where it
    originally came from.
    """

    __tablename__ = "memories"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    kind: Mapped[MemoryKind] = mapped_column(
        _enum_column(MemoryKind), default=MemoryKind.FACT, server_default=MemoryKind.FACT.value
    )
    content: Mapped[str] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(String(200), default=None)  # e.g. "Ram Sharma"

    source_type: Mapped[MemorySource] = mapped_column(_enum_column(MemorySource))
    source_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    source_label: Mapped[str | None] = mapped_column(String(300), default=None)
    confidence: Mapped[float | None] = mapped_column(Float, default=None)  # 0..1, if known
    # How it was extracted, e.g. {"method": "assistant", "provider": "fake"}
    extraction: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )

    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS), deferred=True)

    __table_args__ = (
        Index("ix_memories_workspace_id_kind", "workspace_id", "kind"),
        Index("ix_memories_workspace_id_updated_at", "workspace_id", "updated_at"),
        Index(
            "ix_memories_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
