"""The real Google client: OAuth plus read-only calls to the Gmail, Calendar and
Drive REST APIs over HTTPS.

Nothing here is ever logged except status codes: mail, events and file contents
are personal data.
"""

import base64
import html
import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.integrations.google.types import (
    REQUESTED_SCOPES,
    AwaitingReply,
    CalendarEvent,
    DriveContent,
    DriveFile,
    EmailMessage,
    EmailSummary,
    GoogleApiError,
    GoogleAuthError,
    TokenSet,
)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
CALENDAR = "https://www.googleapis.com/calendar/v3/calendars/primary"
DRIVE = "https://www.googleapis.com/drive/v3"

MAX_BODY_CHARS = 20_000  # per email: keeps what reaches the assistant bounded

_GOOGLE_DOC = "application/vnd.google-apps.document"
_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
# What Drive files can become Veluntra documents: mime type -> (extension, export type)
_IMPORTABLE = {
    _GOOGLE_DOC: (".txt", "text/plain"),  # exported, since Docs have no file bytes
    "application/pdf": (".pdf", None),
    _DOCX: (".docx", None),
    "text/plain": (".txt", None),
    "text/markdown": (".md", None),
}


class UnsupportedDriveFileError(GoogleApiError):
    def __init__(self) -> None:
        super().__init__(
            415, "That file type can't be imported. Supported: Google Docs, PDF, DOCX, TXT and MD."
        )


class DriveFileTooLargeError(GoogleApiError):
    def __init__(self) -> None:
        super().__init__(413, "That file is too large to import.")


def _check(response: httpx.Response) -> None:
    if response.is_success:
        return
    status = response.status_code
    if status == 401:
        raise GoogleAuthError("Google rejected the saved access. Reconnect your Google account.")
    if status == 403:
        raise GoogleApiError(
            403,
            "Google denied access. The permission may not have been granted, or that "
            "Google API is not enabled for the project.",
        )
    if status == 404:
        raise GoogleApiError(404, "Google could not find that item.")
    if status == 429:
        raise GoogleApiError(429, "Google is limiting requests right now. Try again shortly.")
    raise GoogleApiError(status)


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _decode_b64(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _strip_html(markup: str) -> str:
    markup = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", markup)
    markup = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", markup)
    text = html.unescape(re.sub(r"<[^>]+>", " ", markup))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", text)).strip()


def _extract_body(payload: dict[str, Any]) -> str:
    """Plain text of a Gmail message: prefers text/plain parts, falls back to HTML."""
    plain: list[str] = []
    markup: list[str] = []

    def walk(part: dict[str, Any]) -> None:
        mime = part.get("mimeType", "")
        data = (part.get("body") or {}).get("data")
        if data and mime == "text/plain":
            plain.append(_decode_b64(data))
        elif data and mime == "text/html":
            markup.append(_decode_b64(data))
        for child in part.get("parts") or []:
            walk(child)

    walk(payload)
    text = "\n\n".join(plain) if plain else _strip_html("\n".join(markup))
    return text.strip()[:MAX_BODY_CHARS]


def _header(headers: list[dict[str, str]], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _email_summary(raw: dict[str, Any]) -> EmailSummary:
    headers = (raw.get("payload") or {}).get("headers") or []
    internal = raw.get("internalDate")
    return EmailSummary(
        id=raw["id"],
        thread_id=raw.get("threadId", ""),
        sender=_header(headers, "From"),
        subject=_header(headers, "Subject") or "(no subject)",
        date=datetime.fromtimestamp(int(internal) / 1000, UTC) if internal else None,
        snippet=html.unescape(raw.get("snippet", "")),
    )


def _drive_query(query: str) -> str:
    clauses = ["trashed = false"]
    if query.strip():
        escaped = query.strip().replace("\\", "\\\\").replace("'", "\\'")
        clauses.insert(0, f"fullText contains '{escaped}'")
    return " and ".join(clauses)


class HttpGoogleApi:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport  # tests inject a mock transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=httpx.Timeout(15.0), transport=self._transport)

    # --- OAuth ---------------------------------------------------------------------

    def authorization_url(self, state: str) -> str:
        settings = get_settings()
        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": f"{settings.public_backend_url}/api/v1/integrations/google/callback",
            "response_type": "code",
            "scope": " ".join(REQUESTED_SCOPES),
            "state": state,
            "access_type": "offline",  # we need a refresh token to work without the user present
            "prompt": "consent",  # ...and Google only issues one when consent is shown
            "include_granted_scopes": "true",
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    async def _token_request(self, form: dict[str, str]) -> dict[str, Any]:
        settings = get_settings()
        form = {
            **form,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
        }
        async with self._client() as client:
            response = await client.post(TOKEN_URL, data=form)
        if response.status_code == 400 and response.json().get("error") == "invalid_grant":
            raise GoogleAuthError("Google no longer accepts this connection. Reconnect your account.")
        _check(response)
        return response.json()

    @staticmethod
    def _token_set(payload: dict[str, Any], email: str | None = None) -> TokenSet:
        return TokenSet(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_at=datetime.now(UTC) + timedelta(seconds=int(payload.get("expires_in", 3600))),
            scopes=sorted(payload.get("scope", "").split()),
            email=email,
        )

    async def exchange_code(self, code: str) -> TokenSet:
        settings = get_settings()
        payload = await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": f"{settings.public_backend_url}/api/v1/integrations/google/callback",
            }
        )
        email: str | None = None
        try:
            async with self._client() as client:
                info = await client.get(
                    USERINFO_URL, headers={"Authorization": f"Bearer {payload['access_token']}"}
                )
            if info.is_success:
                email = info.json().get("email")
        except httpx.HTTPError:
            pass  # the address is only a label
        return self._token_set(payload, email)

    async def refresh(self, refresh_token: str) -> TokenSet:
        payload = await self._token_request(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}
        )
        return self._token_set(payload)

    async def revoke(self, token: str) -> None:
        async with self._client() as client:
            await client.post(REVOKE_URL, data={"token": token})  # best effort: result ignored

    # --- Gmail -------------------------------------------------------------------------

    async def gmail_search(self, access_token: str, query: str, limit: int) -> Sequence[EmailSummary]:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with self._client() as client:
            listing = await client.get(
                f"{GMAIL}/messages", params={"q": query, "maxResults": limit}, headers=headers
            )
            _check(listing)
            summaries: list[EmailSummary] = []
            for item in listing.json().get("messages", [])[:limit]:
                detail = await client.get(
                    f"{GMAIL}/messages/{item['id']}",
                    params=[
                        ("format", "metadata"),
                        ("metadataHeaders", "From"),
                        ("metadataHeaders", "Subject"),
                    ],
                    headers=headers,
                )
                _check(detail)
                summaries.append(_email_summary(detail.json()))
        return summaries

    async def gmail_get(self, access_token: str, message_id: str) -> EmailMessage:
        async with self._client() as client:
            response = await client.get(
                f"{GMAIL}/messages/{message_id}",
                params={"format": "full"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
        _check(response)
        raw = response.json()
        summary = _email_summary(raw)
        return EmailMessage(
            id=summary.id,
            thread_id=summary.thread_id,
            sender=summary.sender,
            subject=summary.subject,
            date=summary.date,
            snippet=summary.snippet,
            body=_extract_body(raw.get("payload") or {}),
        )

    async def gmail_awaiting_reply(
        self, access_token: str, min_days: int, max_days: int, limit: int
    ) -> Sequence[AwaitingReply]:
        """Threads where the user wrote last, between `min_days` and `max_days` ago."""
        headers = {"Authorization": f"Bearer {access_token}"}
        query = f"in:sent newer_than:{max_days}d older_than:{min_days}d"
        now = datetime.now(UTC)
        waiting: list[AwaitingReply] = []
        async with self._client() as client:
            listing = await client.get(
                f"{GMAIL}/messages",
                params={"q": query, "maxResults": min(limit * 3, 50)},
                headers=headers,
            )
            _check(listing)
            seen: set[str] = set()
            for item in listing.json().get("messages", []):
                thread_id = item.get("threadId")
                if not thread_id or thread_id in seen:
                    continue
                seen.add(thread_id)
                response = await client.get(
                    f"{GMAIL}/threads/{thread_id}",
                    params=[
                        ("format", "metadata"),
                        ("metadataHeaders", "Subject"),
                        ("metadataHeaders", "To"),
                    ],
                    headers=headers,
                )
                _check(response)
                messages = sorted(
                    response.json().get("messages", []), key=lambda m: int(m.get("internalDate", 0))
                )
                if not messages or "SENT" not in messages[-1].get("labelIds", []):
                    continue  # the other side answered last (or the thread is empty)
                last = messages[-1]
                sent_at = datetime.fromtimestamp(int(last["internalDate"]) / 1000, UTC)
                headers_of = lambda m: (m.get("payload") or {}).get("headers") or []  # noqa: E731
                waiting.append(
                    AwaitingReply(
                        thread_id=thread_id,
                        subject=_header(headers_of(messages[0]), "Subject") or "(no subject)",
                        to=_header(headers_of(last), "To"),
                        sent_at=sent_at,
                        days_waiting=(now - sent_at).days,
                    )
                )
                if len(waiting) >= limit:
                    break
        return waiting

    # --- Calendar ------------------------------------------------------------------------

    async def calendar_events(
        self, access_token: str, start: datetime, end: datetime
    ) -> Sequence[CalendarEvent]:
        async with self._client() as client:
            response = await client.get(
                f"{CALENDAR}/events",
                params={
                    "timeMin": start.isoformat(),
                    "timeMax": end.isoformat(),
                    "singleEvents": "true",  # expand recurring events into occurrences
                    "orderBy": "startTime",
                    "maxResults": 100,
                },
                headers={"Authorization": f"Bearer {access_token}"},
            )
        _check(response)
        events: list[CalendarEvent] = []
        for item in response.json().get("items", []):
            if item.get("status") == "cancelled":
                continue
            start_info, end_info = item.get("start", {}), item.get("end", {})
            all_day = "date" in start_info
            attendees = item.get("attendees") or []
            events.append(
                CalendarEvent(
                    id=item["id"],
                    title=item.get("summary") or "(no title)",
                    start=_parse_time(start_info.get("dateTime") or start_info["date"]),
                    end=_parse_time(end_info.get("dateTime") or end_info["date"]),
                    all_day=all_day,
                    location=item.get("location"),
                    attendees=[a["email"] for a in attendees if a.get("email") and not a.get("self")],
                    link=item.get("htmlLink"),
                    declined=any(a.get("self") and a.get("responseStatus") == "declined" for a in attendees),
                )
            )
        return events

    # --- Drive -----------------------------------------------------------------------------

    async def drive_search(self, access_token: str, query: str, limit: int) -> Sequence[DriveFile]:
        async with self._client() as client:
            response = await client.get(
                f"{DRIVE}/files",
                params={
                    "q": _drive_query(query),
                    "pageSize": limit,
                    "orderBy": "modifiedTime desc",
                    "fields": "files(id,name,mimeType,modifiedTime,webViewLink,size)",
                },
                headers={"Authorization": f"Bearer {access_token}"},
            )
        _check(response)
        return [
            DriveFile(
                id=f["id"],
                name=f["name"],
                mime_type=f["mimeType"],
                modified_at=_parse_time(f["modifiedTime"]) if f.get("modifiedTime") else None,
                link=f.get("webViewLink"),
                size=int(f["size"]) if f.get("size") else None,
            )
            for f in response.json().get("files", [])
        ]

    async def drive_download(self, access_token: str, file_id: str, max_bytes: int) -> DriveContent:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with self._client() as client:
            meta = await client.get(
                f"{DRIVE}/files/{file_id}", params={"fields": "id,name,mimeType,size"}, headers=headers
            )
            _check(meta)
            info = meta.json()
            importable = _IMPORTABLE.get(info["mimeType"])
            if importable is None:
                raise UnsupportedDriveFileError()
            extension, export_type = importable
            if info.get("size") and int(info["size"]) > max_bytes:
                raise DriveFileTooLargeError()
            if export_type:
                content = await client.get(
                    f"{DRIVE}/files/{file_id}/export", params={"mimeType": export_type}, headers=headers
                )
            else:
                content = await client.get(
                    f"{DRIVE}/files/{file_id}", params={"alt": "media"}, headers=headers
                )
            _check(content)
        if len(content.content) > max_bytes:
            raise DriveFileTooLargeError()
        name = info["name"]
        if not name.lower().endswith(extension):
            name += extension
        return DriveContent(filename=name, data=content.content)
