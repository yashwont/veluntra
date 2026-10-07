import enum
import uuid
from datetime import datetime

from sqlalchemy import Computed, DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


# Title weighs more than description when ranking search results.
_SEARCH_VECTOR_SQL = (
    "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(description, '')), 'B')"
)


class TaskStatus(enum.StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskPriority(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


def _enum_column(enum_cls: type[enum.StrEnum]) -> Enum:
    """Store enum *values* ("in_progress") as plain strings, not Postgres enums."""
    return Enum(
        enum_cls,
        native_enum=False,
        length=20,
        values_callable=lambda e: [m.value for m in e],
    )


class Task(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tasks"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[TaskStatus] = mapped_column(
        _enum_column(TaskStatus),
        default=TaskStatus.TODO,
        server_default=TaskStatus.TODO.value,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        _enum_column(TaskPriority),
        default=TaskPriority.MEDIUM,
        server_default=TaskPriority.MEDIUM.value,
    )
    due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    # Where the task came from: "manual" now; "assistant", "email", ... later
    source: Mapped[str] = mapped_column(String(30), default="manual", server_default="manual")
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    # Maintained by Postgres on every insert/update; only used inside search queries
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR, Computed(_SEARCH_VECTOR_SQL, persisted=True), deferred=True
    )

    __table_args__ = (
        Index("ix_tasks_search_vector", "search_vector", postgresql_using="gin"),
        # Every query is scoped by workspace, then usually filtered by these
        Index("ix_tasks_workspace_id_status", "workspace_id", "status"),
        Index("ix_tasks_workspace_id_due_date", "workspace_id", "due_date"),
    )
