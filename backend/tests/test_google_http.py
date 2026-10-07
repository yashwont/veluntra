"""The real Google client, exercised against canned Google responses (no network).

These pin down what we send to Google and how we read its answers, since the live
service can't be called from tests.
"""

import base64
import json
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.core.config import get_settings
from app.core.crypto import DecryptionError, _fernet, decrypt, encrypt
from app.integrations.google.http_client import (
    DriveFileTooLargeError,
    HttpGoogleApi,
    UnsupportedDriveFileError,
    _drive_query,
    _extract_body,
    _strip_html,
)
from app.integrations.google.types import (
    REQUESTED_SCOPES,
    SCOPE_CALENDAR,
    SCOPE_DRIVE,
    SCOPE_GMAIL,
    GoogleApiError,
    GoogleAuthError,
)


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "google_client_id", "cid")
    monkeypatch.setattr(settings, "google_client_secret", "csecret")
    monkeypatch.setattr(settings, "public_backend_url", "https://api.example.com")


def api_with(handler) -> tuple[HttpGoogleApi, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return HttpGoogleApi(transport=httpx.MockTransport(record)), seen


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


# --- OAuth -----------------------------------------------------------------------------


def test_authorization_url_asks_for_read_only_offline_access() -> None:
    url = HttpGoogleApi().authorization_url("STATE123")

    parsed = urlparse(url)
    params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://accounts.google.com/o/oauth2/v2/auth"
    assert params["client_id"] == "cid"
    assert params["redirect_uri"] == "https://api.example.com/api/v1/integrations/google/callback"
    assert params["state"] == "STATE123"
    assert params["access_type"] == "offline" and params["prompt"] == "consent"
    scopes = params["scope"].split()
    assert set(scopes) == set(REQUESTED_SCOPES)
    # every data scope is the read-only variant
    assert all(s.endswith(".readonly") for s in scopes if s.startswith("https://"))


async def test_exchange_code_reads_tokens_scopes_and_email() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={
                "access_token": "AT", "refresh_token": "RT", "expires_in": 3599,
                "scope": f"openid email {SCOPE_GMAIL}", "token_type": "Bearer",
            })
        assert request.headers["authorization"] == "Bearer AT"
        return httpx.Response(200, json={"email": "me@gmail.com"})

    api, seen = api_with(handler)

    tokens = await api.exchange_code("the-code")

    form = parse_qs(seen[0].content.decode())
    assert form["code"] == ["the-code"] and form["grant_type"] == ["authorization_code"]
    assert form["client_secret"] == ["csecret"]
    assert form["redirect_uri"] == ["https://api.example.com/api/v1/integrations/google/callback"]
    assert (tokens.access_token, tokens.refresh_token, tokens.email) == ("AT", "RT", "me@gmail.com")
    assert tokens.scopes == sorted(["openid", "email", SCOPE_GMAIL])
    assert 3500 < (tokens.expires_at - datetime.now(UTC)).total_seconds() <= 3599


async def test_exchange_code_survives_a_failing_userinfo_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "AT", "expires_in": 60, "scope": SCOPE_GMAIL})
        return httpx.Response(500)

    tokens = await api_with(handler)[0].exchange_code("c")

    assert tokens.email is None and tokens.refresh_token is None


async def test_refresh_sends_the_refresh_token_and_maps_invalid_grant() -> None:
    api, seen = api_with(lambda r: httpx.Response(200, json={"access_token": "NEW", "expires_in": 3600, "scope": SCOPE_GMAIL}))
    tokens = await api.refresh("RT")
    assert parse_qs(seen[0].content.decode())["refresh_token"] == ["RT"]
    assert tokens.access_token == "NEW" and tokens.refresh_token is None

    revoked, _ = api_with(lambda r: httpx.Response(400, json={"error": "invalid_grant"}))
    with pytest.raises(GoogleAuthError):
        await revoked.refresh("RT")


async def test_revoke_posts_the_token_and_ignores_the_answer() -> None:
    api, seen = api_with(lambda r: httpx.Response(400))

    await api.revoke("RT")

    assert str(seen[0].url) == "https://oauth2.googleapis.com/revoke"
    assert parse_qs(seen[0].content.decode())["token"] == ["RT"]


# --- Gmail --------------------------------------------------------------------------------


async def test_gmail_search_lists_then_fetches_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": "m1", "threadId": "t1"}, {"id": "m2", "threadId": "t2"}]})
        message_id = request.url.path.rsplit("/", 1)[1]
        return httpx.Response(200, json={
            "id": message_id, "threadId": "t-" + message_id, "snippet": "Hi &amp; welcome",
            "internalDate": "1790000000000",
            "payload": {"headers": [{"name": "From", "value": "Ram <ram@abc.test>"}, {"name": "subject", "value": "Proposal"}]},
        })

    api, seen = api_with(handler)

    emails = await api.gmail_search("TOKEN", "from:ram", 5)

    assert seen[0].url.params["q"] == "from:ram" and seen[0].url.params["maxResults"] == "5"
    assert seen[0].headers["authorization"] == "Bearer TOKEN"
    assert seen[1].url.params["format"] == "metadata"
    assert [(e.id, e.sender, e.subject, e.snippet) for e in emails] == [
        ("m1", "Ram <ram@abc.test>", "Proposal", "Hi & welcome"),
        ("m2", "Ram <ram@abc.test>", "Proposal", "Hi & welcome"),
    ]
    assert emails[0].date == datetime.fromtimestamp(1790000000, UTC)


async def test_gmail_search_with_no_results() -> None:
    api, _ = api_with(lambda r: httpx.Response(200, json={"resultSizeEstimate": 0}))

    assert await api.gmail_search("T", "nothing", 5) == []


def test_email_body_prefers_plain_text_from_nested_parts() -> None:
    payload = {"mimeType": "multipart/mixed", "parts": [
        {"mimeType": "multipart/alternative", "parts": [
            {"mimeType": "text/plain", "body": {"data": b64("Plain version")}},
            {"mimeType": "text/html", "body": {"data": b64("<p>HTML version</p>")}},
        ]},
        {"mimeType": "application/pdf", "filename": "x.pdf", "body": {"attachmentId": "a"}},
    ]}

    assert _extract_body(payload) == "Plain version"


def test_email_body_falls_back_to_cleaned_html() -> None:
    markup = "<html><style>p{color:red}</style><body><p>Hello&nbsp;<b>Ram</b></p><script>alert(1)</script><p>Bye</p></body></html>"

    text = _extract_body({"mimeType": "text/html", "body": {"data": b64(markup)}})

    assert "Hello" in text and "Ram" in text and "Bye" in text
    assert "alert" not in text and "color:red" not in text and "<" not in text


def test_email_body_is_capped_and_html_stripper_is_safe_on_junk() -> None:
    assert len(_extract_body({"mimeType": "text/plain", "body": {"data": b64("x" * 100_000)}})) == 20_000
    assert _strip_html("<<<>>> & <unclosed") is not None
    assert _extract_body({}) == ""


# --- Calendar ---------------------------------------------------------------------------------


async def test_calendar_parses_timed_all_day_declined_and_cancelled_events() -> None:
    items = [
        {"id": "e1", "summary": "Standup", "start": {"dateTime": "2026-10-08T09:00:00+05:45"},
         "end": {"dateTime": "2026-10-08T09:30:00+05:45"}, "location": "Room 1", "htmlLink": "https://cal/e1",
         "attendees": [{"email": "me@x.test", "self": True, "responseStatus": "accepted"}, {"email": "ram@x.test"}]},
        {"id": "e2", "start": {"date": "2026-10-09"}, "end": {"date": "2026-10-10"}},
        {"id": "e3", "summary": "Skipped", "start": {"dateTime": "2026-10-08T09:00:00Z"}, "end": {"dateTime": "2026-10-08T10:00:00Z"},
         "attendees": [{"email": "me@x.test", "self": True, "responseStatus": "declined"}]},
        {"id": "e4", "status": "cancelled", "start": {"date": "2026-10-09"}, "end": {"date": "2026-10-10"}},
    ]
    api, seen = api_with(lambda r: httpx.Response(200, json={"items": items}))
    start = datetime(2026, 10, 8, tzinfo=UTC)

    events = await api.calendar_events("T", start, datetime(2026, 10, 15, tzinfo=UTC))

    params = seen[0].url.params
    assert params["singleEvents"] == "true" and params["orderBy"] == "startTime"
    assert params["timeMin"] == start.isoformat()
    assert [e.id for e in events] == ["e1", "e2", "e3"]  # the cancelled one is gone
    e1, e2, e3 = events
    assert e1.title == "Standup" and e1.attendees == ["ram@x.test"] and e1.location == "Room 1"
    assert e1.start.utcoffset().total_seconds() == 5.75 * 3600
    assert e2.all_day and e2.title == "(no title)"
    assert e3.declined and not e1.declined


# --- Drive -------------------------------------------------------------------------------------


def test_drive_query_escapes_quotes_and_backslashes() -> None:
    assert _drive_query("") == "trashed = false"
    assert _drive_query("budget") == "fullText contains 'budget' and trashed = false"
    assert _drive_query("o'brien \\ x") == "fullText contains 'o\\'brien \\\\ x' and trashed = false"


async def test_drive_search_parses_files() -> None:
    files = {"files": [
        {"id": "f1", "name": "Budget", "mimeType": "application/vnd.google-apps.document",
         "modifiedTime": "2026-10-01T10:00:00.000Z", "webViewLink": "https://drive/f1"},
        {"id": "f2", "name": "scan.pdf", "mimeType": "application/pdf", "size": "2048"},
    ]}
    api, seen = api_with(lambda r: httpx.Response(200, json=files))

    found = await api.drive_search("T", "budget", 5)

    assert seen[0].url.params["pageSize"] == "5"
    assert "fullText contains 'budget'" in seen[0].url.params["q"]
    assert [(f.id, f.size, f.link) for f in found] == [("f1", None, "https://drive/f1"), ("f2", 2048, None)]
    assert found[0].modified_at == datetime(2026, 10, 1, 10, tzinfo=UTC)


def drive_handler(info: dict, content: bytes = b"hello"):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("fields"):
            return httpx.Response(200, json=info)
        return httpx.Response(200, content=content)

    return handler


async def test_drive_download_exports_google_docs_as_text() -> None:
    api, seen = api_with(drive_handler({"id": "f1", "name": "Plan", "mimeType": "application/vnd.google-apps.document"}, b"exported"))

    content = await api.drive_download("T", "f1", 1_000_000)

    assert seen[1].url.path.endswith("/f1/export") and seen[1].url.params["mimeType"] == "text/plain"
    assert (content.filename, content.data) == ("Plan.txt", b"exported")


async def test_drive_download_fetches_binary_files_as_is() -> None:
    api, seen = api_with(drive_handler({"id": "f2", "name": "report.pdf", "mimeType": "application/pdf", "size": "5"}, b"%PDF-"))

    content = await api.drive_download("T", "f2", 1_000_000)

    assert seen[1].url.params["alt"] == "media"
    assert (content.filename, content.data) == ("report.pdf", b"%PDF-")


async def test_drive_download_refuses_unsupported_and_oversized_files() -> None:
    sheet = api_with(drive_handler({"id": "s", "name": "S", "mimeType": "application/vnd.google-apps.spreadsheet"}))[0]
    big = api_with(drive_handler({"id": "b", "name": "b.pdf", "mimeType": "application/pdf", "size": "999999"}))[0]
    grew = api_with(drive_handler({"id": "g", "name": "g.txt", "mimeType": "text/plain"}, b"x" * 100))[0]

    with pytest.raises(UnsupportedDriveFileError):
        await sheet.drive_download("T", "s", 1000)
    with pytest.raises(DriveFileTooLargeError):
        await big.drive_download("T", "b", 1000)
    with pytest.raises(DriveFileTooLargeError):  # size unknown up front, too big once downloaded
        await grew.drive_download("T", "g", 50)


# --- Error mapping ------------------------------------------------------------------------------


@pytest.mark.parametrize("status,error,fragment", [
    (401, GoogleAuthError, "Reconnect"),
    (403, GoogleApiError, "denied"),
    (404, GoogleApiError, "could not find"),
    (429, GoogleApiError, "limiting"),
    (500, GoogleApiError, "could not complete"),
])
async def test_http_errors_become_safe_messages(status, error, fragment) -> None:
    api, _ = api_with(lambda r: httpx.Response(status, json={"error": {"message": "SECRET INTERNAL DETAIL"}}))

    with pytest.raises(error) as caught:
        await api.drive_search("T", "x", 5)

    assert fragment in str(caught.value)
    assert "SECRET" not in str(caught.value)
    if error is GoogleApiError:
        assert caught.value.status == status


# --- Token encryption -------------------------------------------------------------------------------


def test_encryption_round_trips_and_hides_the_value() -> None:
    secret = "ya29.a0-very-secret-token"

    stored = encrypt(secret)

    assert secret not in stored
    assert decrypt(stored) == secret
    assert encrypt(secret) != stored  # fresh randomness each time


def test_decrypting_with_a_different_key_fails_cleanly(monkeypatch) -> None:
    stored = encrypt("token")
    settings = get_settings()
    monkeypatch.setattr(settings, "secret_key", "a-completely-different-secret-key-value")
    _fernet.cache_clear()
    try:
        with pytest.raises(DecryptionError):
            decrypt(stored)
    finally:
        monkeypatch.undo()
        _fernet.cache_clear()
    assert decrypt(stored) == "token"


def test_a_dedicated_encryption_key_is_used_when_configured(monkeypatch) -> None:
    from cryptography.fernet import Fernet

    stored = encrypt("token")
    monkeypatch.setattr(get_settings(), "integration_encryption_key", Fernet.generate_key().decode())
    _fernet.cache_clear()
    try:
        with pytest.raises(DecryptionError):
            decrypt(stored)  # a different key can't read what the derived key wrote
        assert decrypt(encrypt("other")) == "other"
    finally:
        monkeypatch.undo()
        _fernet.cache_clear()
    assert json.dumps(SCOPE_DRIVE) and SCOPE_CALENDAR  # scopes stay importable constants
