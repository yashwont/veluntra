import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class IntegrationProvider(enum.StrEnum):
    GOOGLE = "google"


class IntegrationStatus(enum.StrEnum):
    ACTIVE = "active"
    NEEDS_REAUTH = "needs_reauth"  # access was revoked or expired: the user must reconnect


class IntegrationAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One user's connection to an external account (their Google account).

    Personal: the tokens belong to `user_id`, and only that user's requests may use
    them, even though the row lives in a workspace. Tokens are stored encrypted.
    """

    __tablename__ = "integration_accounts"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[IntegrationProvider] = mapped_column(
        Enum(
            IntegrationProvider,
            native_enum=False,
            length=20,
            values_callable=lambda e: [m.value for m in e],
        )
    )
    account_email: Mapped[str | None] = mapped_column(String(320), default=None)
    # The permissions actually granted (the user can untick some on Google's screen)
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(String(300)), default=list, server_default=text("'{}'")
    )
    access_token_encrypted: Mapped[str] = mapped_column(Text)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, default=None)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[IntegrationStatus] = mapped_column(
        Enum(
            IntegrationStatus,
            native_enum=False,
            length=20,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=IntegrationStatus.ACTIVE,
        server_default=IntegrationStatus.ACTIVE.value,
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", "provider"),
    )
