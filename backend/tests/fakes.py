"""Test doubles for the LLM provider."""

import uuid
from collections.abc import Sequence
from typing import Any

from app.llm.types import LLMResponse, LLMTurn, ToolCall, ToolDefinition


def say(text: str) -> LLMResponse:
    return LLMResponse(text=text)


def call_tool(name: str, arguments: dict[str, Any], text: str = "") -> LLMResponse:
    return LLMResponse(
        text=text,
        tool_calls=[ToolCall(id=f"call_{uuid.uuid4().hex[:8]}", name=name, input=arguments)],
        stop_reason="tool_use",
    )


class ScriptedProvider:
    """Plays back prepared responses (or raises prepared exceptions) in order, and
    records what the app sent so tests can assert on it."""

    name = "scripted"

    def __init__(self, *script: LLMResponse | Exception, then: LLMResponse | None = None) -> None:
        self._script = list(script)
        self._then = then  # returned forever once the script runs out
        self.calls: list[dict[str, Any]] = []

    async def generate(
        self,
        *,
        system: str,
        turns: Sequence[LLMTurn],
        tools: Sequence[ToolDefinition],
    ) -> LLMResponse:
        self.calls.append({"system": system, "turns": list(turns), "tools": list(tools)})
        if self._script:
            item = self._script.pop(0)
        elif self._then is not None:
            item = self._then
        else:
            raise AssertionError("ScriptedProvider ran out of responses")
        if isinstance(item, Exception):
            raise item
        return item


# --- Google ----------------------------------------------------------------------------

from datetime import UTC, datetime, timedelta  # noqa: E402

from app.integrations.google.types import (  # noqa: E402
    REQUESTED_SCOPES,
    CalendarEvent,
    DriveContent,
    DriveFile,
    EmailMessage,
    EmailSummary,
    GoogleApiError,
    GoogleAuthError,
    TokenSet,
)


def make_tokens(**overrides: Any) -> TokenSet:
    values: dict[str, Any] = {
        "access_token": "access-1",
        "refresh_token": "refresh-1",
        "expires_at": datetime.now(UTC) + timedelta(hours=1),
        "scopes": sorted(REQUESTED_SCOPES),
        "email": "me@gmail.test",
    }
    values.update(overrides)
    return TokenSet(**values)


class FakeGoogleApi:
    """Stands in for Google: canned data, and a record of every call and token used."""

    def __init__(self) -> None:
        self.tokens = make_tokens()
        self.refreshed_tokens = make_tokens(access_token="access-2", refresh_token=None)
        self.refresh_error: Exception | None = None
        self.data_error: Exception | None = None  # raised by every data call
        self.emails: list[EmailSummary] = []
        self.email_bodies: dict[str, str] = {}
        self.events: list[CalendarEvent] = []
        self.files: list[DriveFile] = []
        self.downloads: dict[str, DriveContent | Exception] = {}
        self.revoked: list[str] = []
        self.refresh_calls: list[str] = []
        self.tokens_used: list[str] = []

    # --- OAuth
    def authorization_url(self, state: str) -> str:
        return f"https://accounts.example/auth?state={state}"

    async def exchange_code(self, code: str) -> TokenSet:
        if code == "bad":
            raise GoogleAuthError("code rejected")
        return self.tokens

    async def refresh(self, refresh_token: str) -> TokenSet:
        self.refresh_calls.append(refresh_token)
        if self.refresh_error:
            raise self.refresh_error
        return self.refreshed_tokens

    async def revoke(self, token: str) -> None:
        self.revoked.append(token)

    # --- Data
    def _use(self, token: str) -> None:
        self.tokens_used.append(token)
        if self.data_error:
            raise self.data_error

    async def gmail_search(self, access_token: str, query: str, limit: int):
        self._use(access_token)
        return [m for m in self.emails if query.lower() in (m.subject + m.sender + m.snippet).lower()][:limit]

    async def gmail_get(self, access_token: str, message_id: str) -> EmailMessage:
        self._use(access_token)
        for m in self.emails:
            if m.id == message_id:
                return EmailMessage(**{**m.__dict__, "body": self.email_bodies.get(m.id, "")})
        raise GoogleApiError(404, "Google could not find that item.")

    async def calendar_events(self, access_token: str, start: datetime, end: datetime):
        self._use(access_token)
        return [e for e in self.events if e.start < end and e.end > start]

    async def drive_search(self, access_token: str, query: str, limit: int):
        self._use(access_token)
        return [f for f in self.files if query.lower() in f.name.lower()][:limit]

    async def drive_download(self, access_token: str, file_id: str, max_bytes: int) -> DriveContent:
        self._use(access_token)
        result = self.downloads[file_id]
        if isinstance(result, Exception):
            raise result
        return result
