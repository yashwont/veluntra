import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AuthenticationError, ConflictError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    password_needs_rehash,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.repositories.refresh_tokens import RefreshTokenRepository
from app.repositories.users import UserRepository
from app.repositories.workspaces import WorkspaceRepository
from app.schemas.auth import TokenPair

logger = logging.getLogger(__name__)

# Verified against when the email is unknown, so "no such user" costs the same
# time as "wrong password" and response timing doesn't reveal which emails exist.
_DUMMY_HASH = hash_password("dummy-password-for-timing")


class EmailAlreadyRegisteredError(ConflictError):
    code = "EMAIL_ALREADY_REGISTERED"
    message = "An account with this email already exists."


class InvalidCredentialsError(AuthenticationError):
    code = "INVALID_CREDENTIALS"
    message = "Incorrect email or password."


class InvalidRefreshTokenError(AuthenticationError):
    code = "INVALID_REFRESH_TOKEN"
    message = "Invalid or expired token."


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.workspaces = WorkspaceRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)

    async def register(self, email: str, password: str, full_name: str) -> User:
        """Create a user plus a personal workspace they own."""
        email = email.strip().lower()
        if await self.users.get_by_email(email) is not None:
            raise EmailAlreadyRegisteredError()

        # Argon2 is CPU-heavy; run it off the event loop
        password_hash = await asyncio.to_thread(hash_password, password)
        user = User(email=email, password_hash=password_hash, full_name=full_name)
        workspace = Workspace(name=f"{full_name}'s Workspace")
        self.users.add(user)
        self.workspaces.add(workspace)
        try:
            await self.session.flush()  # assigns ids; unique violation surfaces here
            self.workspaces.add_member(
                WorkspaceMember(
                    workspace_id=workspace.id,
                    user_id=user.id,
                    role=WorkspaceRole.OWNER,
                )
            )
            await self.session.commit()
        except IntegrityError:
            # Two concurrent registrations with the same email
            await self.session.rollback()
            raise EmailAlreadyRegisteredError() from None

        logger.info("user registered", extra={"user_id": str(user.id)})
        return user

    async def login(self, email: str, password: str) -> TokenPair:
        user = await self.users.get_by_email(email.strip().lower())
        if user is None:
            await asyncio.to_thread(verify_password, password, _DUMMY_HASH)
            logger.warning("login failed", extra={"reason": "unknown_email"})
            raise InvalidCredentialsError()

        valid = await asyncio.to_thread(verify_password, password, user.password_hash)
        if not valid or not user.is_active:
            logger.warning(
                "login failed",
                extra={"reason": "bad_password_or_inactive", "user_id": str(user.id)},
            )
            raise InvalidCredentialsError()

        if password_needs_rehash(user.password_hash):
            user.password_hash = await asyncio.to_thread(hash_password, password)

        tokens = self._issue_tokens(user)
        await self.session.commit()
        logger.info("login succeeded", extra={"user_id": str(user.id)})
        return tokens

    async def refresh(self, refresh_token: str) -> TokenPair:
        """Exchange a refresh token for a new pair (the old one is revoked)."""
        claims = decode_token(refresh_token, "refresh")
        try:
            stored = await self.refresh_tokens.get(uuid.UUID(claims["jti"]))
        except ValueError:
            raise InvalidRefreshTokenError() from None
        if stored is None:
            raise InvalidRefreshTokenError()

        if stored.revoked_at is not None:
            # A rotated/revoked token came back: it may have been stolen.
            # Kill every session for this user.
            await self.refresh_tokens.revoke_all_for_user(stored.user_id)
            await self.session.commit()
            logger.warning(
                "refresh token reuse detected", extra={"user_id": str(stored.user_id)}
            )
            raise InvalidRefreshTokenError()

        user = await self.users.get_by_id(stored.user_id)
        if user is None or not user.is_active:
            raise InvalidRefreshTokenError()

        stored.revoked_at = datetime.now(timezone.utc)
        tokens = self._issue_tokens(user)
        await self.session.commit()
        return tokens

    async def logout(self, refresh_token: str) -> None:
        """Revoke a refresh token. Safe to call twice."""
        claims = decode_token(refresh_token, "refresh")
        try:
            stored = await self.refresh_tokens.get(uuid.UUID(claims["jti"]))
        except ValueError:
            return
        if stored is not None and stored.revoked_at is None:
            stored.revoked_at = datetime.now(timezone.utc)
            await self.session.commit()

    def _issue_tokens(self, user: User) -> TokenPair:
        settings = get_settings()
        access = create_access_token(str(user.id))
        refresh = create_refresh_token(str(user.id))
        self.refresh_tokens.add(
            RefreshToken(
                id=uuid.UUID(refresh.jti),
                user_id=user.id,
                expires_at=refresh.expires_at,
            )
        )
        return TokenPair(
            access_token=access,
            refresh_token=refresh.token,
            expires_in=settings.access_token_expire_minutes * 60,
        )
