from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import DecryptionError, decrypt, encrypt
from app.core.errors import AppError, AuthenticationError, ConflictError, NotFoundError
from app.core.security import create_oauth_state, decode_oauth_state
from app.integrations.google.calendar import find_conflicts
from app.integrations.google.types import (
    SCOPE_CALENDAR,
    SCOPE_DRIVE,
    SCOPE_GMAIL,
    CalendarEvent,
    DriveFile,
    EmailMessage,
    EmailSummary,
    GoogleApi,
    GoogleApiError,
    GoogleAuthError,
)
from app.models.document import Document
from app.models.integration import IntegrationAccount, IntegrationProvider, IntegrationStatus
from app.repositories.integrations import IntegrationRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.document_service import DocumentService

logger = logging.getLogger(__name__)
T = TypeVar("T")

# Refresh a little early so a token never expires mid-request
EXPIRY_MARGIN = timedelta(seconds=60)
DATA_SCOPES = (SCOPE_GMAIL, SCOPE_CALENDAR, SCOPE_DRIVE)


class IntegrationNotConfiguredError(ConflictError):
    code = "INTEGRATION_NOT_CONFIGURED"
    message = (
        "Google isn't set up on this server yet. An administrator needs to add a Google "
        "client ID and secret (see docs/GOOGLE_SETUP.md)."
    )


class NotConnectedError(ConflictError):
    code = "GOOGLE_NOT_CONNECTED"
    message = "Your Google account isn't connected. Connect it on the Connections page."


class ReauthRequiredError(ConflictError):
    code = "GOOGLE_REAUTH_REQUIRED"
    message = "Google no longer accepts this connection. Reconnect your Google account."


class ScopeNotGrantedError(ConflictError):
    code = "GOOGLE_SCOPE_MISSING"
    message = "You didn't allow that access when connecting. Reconnect and tick the permission."


class InvalidOAuthStateError(AppError):
    code = "INVALID_OAUTH_STATE"
    message = "The connection attempt is invalid or has expired. Please try again."


class OAuthIncompleteError(AppError):
    code = "OAUTH_INCOMPLETE"
    message = "Google didn't grant the access needed. Try again and allow the requested permissions."


class IntegrationNotFoundError(NotFoundError):
    code = "INTEGRATION_NOT_FOUND"
    message = "The requested connection does not exist."


_GOOGLE_ERRORS = {
    404: (404, "GOOGLE_ITEM_NOT_FOUND"),
    413: (413, "GOOGLE_FILE_TOO_LARGE"),
    415: (422, "GOOGLE_UNSUPPORTED_FILE"),
    429: (429, "GOOGLE_RATE_LIMITED"),
}


class GoogleRequestError(AppError):
    """Google itself failed or refused (not our credentials): shown with a safe message."""

    def __init__(self, error: GoogleApiError) -> None:
        super().__init__(str(error))
        self.status_code, self.code = _GOOGLE_ERRORS.get(error.status, (502, "GOOGLE_ERROR"))


class IntegrationService:
    """A user's connection to Google, and read-only access to their mail, calendar
    and Drive through it.

    The caller must already have verified the user belongs to `workspace_id`.
    """

    def __init__(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        google: GoogleApi,
    ) -> None:
        self.session = session
        self.workspace_id = workspace_id
        self.user_id = user_id
        self.google = google
        self.accounts = IntegrationRepository(session)

    # --- Connecting ------------------------------------------------------------------

    async def list_accounts(self) -> list[IntegrationAccount]:
        return await self.accounts.list_for_user(self.workspace_id, self.user_id)

    def begin_connect(self) -> str:
        """The Google consent URL for this user. The signed `state` ties Google's
        answer to this user and workspace."""
        if not get_settings().google_configured:
            raise IntegrationNotConfiguredError()
        return self.google.authorization_url(create_oauth_state(self.user_id, self.workspace_id))

    @staticmethod
    async def complete_connect(
        session: AsyncSession, google: GoogleApi, *, code: str, state: str
    ) -> IntegrationAccount:
        """Finish the OAuth flow when Google redirects back. There is no logged-in
        request here (it is a browser redirect), so identity comes from the signed state."""
        if not get_settings().google_configured:
            raise IntegrationNotConfiguredError()
        try:
            user_id, workspace_id = decode_oauth_state(state)
        except AuthenticationError:
            raise InvalidOAuthStateError() from None
        # The user must still belong to the workspace the flow was started for
        if await WorkspaceRepository(session).get_membership(workspace_id, user_id) is None:
            raise InvalidOAuthStateError()

        try:
            tokens = await google.exchange_code(code)
        except GoogleAuthError:
            raise InvalidOAuthStateError() from None  # expired or reused code
        except GoogleApiError as exc:
            raise GoogleRequestError(exc) from exc
        if not any(scope in tokens.scopes for scope in DATA_SCOPES):
            raise OAuthIncompleteError()

        repo = IntegrationRepository(session)
        account = await repo.get_for_provider(workspace_id, user_id, IntegrationProvider.GOOGLE)
        if account is None:
            if tokens.refresh_token is None:
                raise OAuthIncompleteError()  # without it the connection dies within the hour
            account = IntegrationAccount(
                workspace_id=workspace_id, user_id=user_id, provider=IntegrationProvider.GOOGLE
            )
            repo.add(account)
        account.account_email = tokens.email or account.account_email
        account.scopes = tokens.scopes
        account.access_token_encrypted = encrypt(tokens.access_token)
        if tokens.refresh_token:
            account.refresh_token_encrypted = encrypt(tokens.refresh_token)
        account.token_expires_at = tokens.expires_at
        account.status = IntegrationStatus.ACTIVE
        await session.commit()
        await session.refresh(account)
        logger.info(
            "integration connected",
            extra={"provider": "google", "workspace_id": str(workspace_id), "user_id": str(user_id)},
        )
        return account

    async def disconnect(self, account_id: uuid.UUID) -> None:
        account = await self.accounts.get(self.workspace_id, self.user_id, account_id)
        if account is None:
            raise IntegrationNotFoundError()
        # Take back the access at Google too, so deleting our copy isn't the only safeguard
        try:
            token = decrypt(account.refresh_token_encrypted or account.access_token_encrypted)
            await self.google.revoke(token)
        except Exception:  # best effort: the user still wants it gone from here
            logger.warning("could not revoke google token", extra={"account_id": str(account_id)})
        await self.accounts.delete(account)
        await self.session.commit()
        logger.info(
            "integration disconnected",
            extra={"provider": "google", "workspace_id": str(self.workspace_id)},
        )

    # --- Access tokens -----------------------------------------------------------------

    async def _mark_reauth(self, account: IntegrationAccount) -> ReauthRequiredError:
        account.status = IntegrationStatus.NEEDS_REAUTH
        await self.session.commit()
        return ReauthRequiredError()

    async def _access_token(self, scope: str) -> tuple[IntegrationAccount, str]:
        account = await self.accounts.get_for_provider(
            self.workspace_id, self.user_id, IntegrationProvider.GOOGLE
        )
        if account is None:
            raise NotConnectedError()
        if account.status == IntegrationStatus.NEEDS_REAUTH:
            raise ReauthRequiredError()
        if scope not in account.scopes:
            raise ScopeNotGrantedError()

        try:
            if account.token_expires_at - datetime.now(UTC) > EXPIRY_MARGIN:
                return account, decrypt(account.access_token_encrypted)
            if account.refresh_token_encrypted is None:
                raise await self._mark_reauth(account)
            tokens = await self.google.refresh(decrypt(account.refresh_token_encrypted))
        except (GoogleAuthError, DecryptionError):
            raise await self._mark_reauth(account) from None
        except GoogleApiError as exc:
            raise GoogleRequestError(exc) from exc

        account.access_token_encrypted = encrypt(tokens.access_token)
        account.token_expires_at = tokens.expires_at
        if tokens.refresh_token:
            account.refresh_token_encrypted = encrypt(tokens.refresh_token)
        await self.session.commit()
        return account, tokens.access_token

    async def _call(self, scope: str, action: Callable[[str], Awaitable[T]]) -> T:
        """Run a Google call with a valid token, translating failures into app errors."""
        account, token = await self._access_token(scope)
        try:
            return await action(token)
        except GoogleAuthError:
            raise await self._mark_reauth(account) from None
        except GoogleApiError as exc:
            raise GoogleRequestError(exc) from exc

    # --- Reading (never writing) --------------------------------------------------------

    async def gmail_search(self, query: str, limit: int) -> Sequence[EmailSummary]:
        return await self._call(SCOPE_GMAIL, lambda t: self.google.gmail_search(t, query, limit))

    async def gmail_read(self, message_id: str) -> EmailMessage:
        return await self._call(SCOPE_GMAIL, lambda t: self.google.gmail_get(t, message_id))

    async def calendar(
        self, start: datetime, end: datetime
    ) -> tuple[Sequence[CalendarEvent], list[tuple[CalendarEvent, CalendarEvent]]]:
        events = await self._call(
            SCOPE_CALENDAR, lambda t: self.google.calendar_events(t, start, end)
        )
        return events, find_conflicts(events)

    async def drive_search(self, query: str, limit: int) -> Sequence[DriveFile]:
        return await self._call(SCOPE_DRIVE, lambda t: self.google.drive_search(t, query, limit))

    async def drive_import(self, file_id: str) -> Document:
        """Copy a Drive file into Veluntra's documents (so it becomes searchable).
        Processing is started by the caller, as for any upload."""
        max_bytes = get_settings().max_upload_bytes
        content = await self._call(
            SCOPE_DRIVE, lambda t: self.google.drive_download(t, file_id, max_bytes)
        )
        return await DocumentService(self.session, self.workspace_id).upload(
            filename=content.filename, data=content.data, user_id=self.user_id
        )
