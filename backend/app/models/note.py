import uuid

from sqlalchemy import Computed, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin

# Title weighs more than content when ranking search results.
_SEARCH_VECTOR_SQL = (
    "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(content, '')), 'B')"
)


class Note(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notes"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text, default="", server_default="")
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), default=list, server_default=text("'{}'")
    )
    # Maintained by Postgres on every insert/update. Never loaded into Python
    # (deferred); only used inside search queries.
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR, Computed(_SEARCH_VECTOR_SQL, persisted=True), deferred=True
    )

    __table_args__ = (
        Index("ix_notes_workspace_id_updated_at", "workspace_id", "updated_at"),
        Index("ix_notes_tags", "tags", postgresql_using="gin"),
        Index("ix_notes_search_vector", "search_vector", postgresql_using="gin"),
    )
