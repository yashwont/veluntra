import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.task import TaskPriority


class SuggestionStatus(enum.StrEnum):
    PENDING = "pending"  # waiting for the user to accept or dismiss
    ACCEPTED = "accepted"  # became a task
    DISMISSED = "dismissed"


class SuggestionKind(enum.StrEnum):
    EMAIL_ACTION = "email_action"  # an email asks the user to do something
    EMAIL_FOLLOW_UP = "email_follow_up"  # the user wrote last and nobody answered


def _enum_column(enum_cls: type[enum.StrEnum]) -> Enum:
    return Enum(
        enum_cls,
        native_enum=False,
        length=20,
        values_callable=lambda e: [m.value for m in e],
    )


class Suggestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A task Veluntra *proposes*, found in the user's email. Nothing becomes a real
    task until the user accepts it. Personal: only its owner sees or acts on it."""

    __tablename__ = "suggestions"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[SuggestionKind] = mapped_column(_enum_column(SuggestionKind))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(
            TaskPriority,
            native_enum=False,
            length=20,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=TaskPriority.MEDIUM,
    )
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    reason: Mapped[str] = mapped_column(String(500))  # why this was suggested
    confidence: Mapped[float | None] = mapped_column(Float, default=None)

    # Provenance: which email (or thread) it came from
    source_type: Mapped[str] = mapped_column(String(30))
    source_id: Mapped[str] = mapped_column(String(200))
    source_label: Mapped[str | None] = mapped_column(String(300), default=None)

    status: Mapped[SuggestionStatus] = mapped_column(
        _enum_column(SuggestionStatus),
        default=SuggestionStatus.PENDING,
        server_default=SuggestionStatus.PENDING.value,
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), default=None
    )

    __table_args__ = (
        # One suggestion per email and kind, ever: a dismissed one is not resurrected
        UniqueConstraint("workspace_id", "user_id", "kind", "source_type", "source_id"),
        Index("ix_suggestions_workspace_id_user_id_status", "workspace_id", "user_id", "status"),
    )
