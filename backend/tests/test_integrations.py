import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.config import get_settings
from app.core.security import create_oauth_state
from app.db.session import SessionLocal
from app.integrations.google.calendar import find_conflicts
from app.integrations.google.http_client import DriveFileTooLargeError, UnsupportedDriveFileError
from app.integrations.google.types import (
    SCOPE_CALENDAR,
    SCOPE_EMAIL,
    SCOPE_OPENID,
    CalendarEvent,
    DriveContent,
    DriveFile,
    EmailSummary,
    GoogleApiError,
    GoogleAuthError,
)
from tests.fakes import make_tokens

CALLBACK = "/api/v1/integrations/google/callback"


def base(workspace_id: str) -> str:
    return f"/api/v1/workspaces/{workspace_id}/integrations"


async def connect(client: AsyncClient, user, code: str = "good") -> str:
    """Runs the whole OAuth round trip and returns where the browser is sent next."""
    started = await client.post(f"{base(user.workspace_id)}/google/connect", headers=user.headers)
    assert started.status_code == 200, started.text
    state = parse_qs(urlparse(started.json()["authorization_url"]).query)["state"][0]
    response = await client.get(CALLBACK, params={"code": code, "state": state})
    assert response.status_code == 307
    return response.headers["location"]


async def accounts(client: AsyncClient, user) -> dict:
    response = await client.get(base(user.workspace_id), headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


def at(hour: int, minute: int = 0, day: int = 0) -> datetime:
    return (datetime.now(UTC) + timedelta(days=day)).replace(hour=hour, minute=minute, second=0, microsecond=0)


def event(id: str, title: str, start: datetime, end: datetime, **kw) -> CalendarEvent:
    return CalendarEvent(id=id, title=title, start=start, end=end, all_day=kw.pop("all_day", False), **kw)


def email(id: str, subject: str, sender: str = "Ram <ram@abc.test>", snippet: str = "") -> EmailSummary:
    return EmailSummary(id=id, thread_id="t-" + id, sender=sender, subject=subject, date=at(9), snippet=snippet)


# --- Calendar conflicts (pure logic) -----------------------------------------------------


def test_overlapping_events_conflict() -> None:
    a = event("a", "Standup", at(9), at(10))
    b = event("b", "Review", at(9, 30), at(10, 30))
    c = event("c", "Lunch", at(12), at(13))

    assert [(x.id, y.id) for x, y in find_conflicts([c, b, a])] == [("a", "b")]


def test_back_to_back_events_do_not_conflict() -> None:
    assert find_conflicts([event("a", "A", at(9), at(10)), event("b", "B", at(10), at(11))]) == []


def test_all_day_and_declined_events_never_conflict() -> None:
    meeting = event("m", "Meeting", at(9), at(10))
    banner = event("d", "Holiday", at(0), at(23, 59), all_day=True)
    declined = event("x", "Declined sync", at(9), at(10), declined=True)

    assert find_conflicts([meeting, banner, declined]) == []


def test_one_event_can_clash_with_several() -> None:
    long = event("long", "Workshop", at(9), at(17))
    short1 = event("s1", "Call", at(10), at(11))
    short2 = event("s2", "Call 2", at(14), at(15))

    pairs = {(x.id, y.id) for x, y in find_conflicts([long, short1, short2])}

    assert pairs == {("long", "s1"), ("long", "s2")}


# --- Connecting ------------------------------------------------------------------------------


async def test_unconfigured_server_cannot_connect(make_user, client) -> None:
    alice = await make_user()

    listing = await accounts(client, alice)
    response = await client.post(f"{base(alice.workspace_id)}/google/connect", headers=alice.headers)

    assert listing == {"google_configured": False, "accounts": []}
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INTEGRATION_NOT_CONFIGURED"


async def test_connect_flow_stores_an_encrypted_connection(make_user, client, google) -> None:
    alice = await make_user()

    started = await client.post(f"{base(alice.workspace_id)}/google/connect", headers=alice.headers)
    assert started.status_code == 200
    assert started.json()["authorization_url"].startswith("https://accounts.example/auth?state=")
    location = await connect(client, alice)

    assert location == "http://localhost:3000/integrations?google=connected"
    listing = await accounts(client, alice)
    assert listing["google_configured"] is True
    [account] = listing["accounts"]
    assert account["provider"] == "google"
    assert account["account_email"] == "me@gmail.test"
    assert account["status"] == "active"
    assert account["gmail"] and account["calendar"] and account["drive"]
    assert "token" not in str(account).lower()
    async with SessionLocal() as session:
        row = (
            await session.execute(
                text("SELECT access_token_encrypted AS a, refresh_token_encrypted AS r FROM integration_accounts")
            )
        ).one()
    assert "access-1" not in row.a and "refresh-1" not in row.r  # stored encrypted, not as given


async def test_reconnecting_updates_the_same_connection(make_user, client, google) -> None:
    alice = await make_user()
    await connect(client, alice)
    google.tokens = make_tokens(access_token="access-9", refresh_token=None, email="new@gmail.test")

    await connect(client, alice)

    [account] = (await accounts(client, alice))["accounts"]
    assert account["account_email"] == "new@gmail.test"
    async with SessionLocal() as session:
        assert await session.scalar(text("SELECT count(*) FROM integration_accounts")) == 1


@pytest.mark.parametrize("tokens", [
    {"refresh_token": None},  # first connection without a refresh token would die in an hour
    {"scopes": ["openid", "email"]},  # user unticked every data permission
])
async def test_incomplete_grants_are_refused(make_user, client, google, tokens) -> None:
    alice = await make_user()
    google.tokens = make_tokens(**tokens)

    location = await connect(client, alice)

    assert location.endswith("?google=error&reason=OAUTH_INCOMPLETE")
    assert (await accounts(client, alice))["accounts"] == []


async def test_callback_rejects_bad_state_and_codes(make_user, client, google) -> None:
    alice = await make_user()
    user_id, ws = uuid.UUID(alice.user_id), uuid.UUID(alice.workspace_id)
    good_state = create_oauth_state(user_id, ws)
    expired = jwt.encode(
        {"sub": str(user_id), "ws": str(ws), "type": "oauth_state", "jti": "x",
         "iat": datetime.now(UTC) - timedelta(hours=1), "exp": datetime.now(UTC) - timedelta(minutes=30)},
        get_settings().secret_key, algorithm="HS256",
    )
    forged = jwt.encode(
        {"sub": str(user_id), "ws": str(ws), "type": "oauth_state", "jti": "x",
         "iat": datetime.now(UTC), "exp": datetime.now(UTC) + timedelta(minutes=5)},
        "attacker-key-attacker-key-attacker-key", algorithm="HS256",
    )
    stranger = create_oauth_state(uuid.uuid4(), ws)  # a user who is not in that workspace
    from app.core.security import create_access_token

    cases = {
        "garbage": {"code": "good", "state": "not-a-token"},
        "expired": {"code": "good", "state": expired},
        "forged": {"code": "good", "state": forged},
        "stranger": {"code": "good", "state": stranger},
        "access token as state": {"code": "good", "state": create_access_token(alice.user_id)},
        "rejected code": {"code": "bad", "state": good_state},
    }
    for name, params in cases.items():
        response = await client.get(CALLBACK, params=params)
        assert response.status_code == 307, name
        assert response.headers["location"].endswith("reason=INVALID_OAUTH_STATE"), name
    assert (await accounts(client, alice))["accounts"] == []


async def test_callback_handles_denial_and_missing_params(make_user, client, google) -> None:
    denied = await client.get(CALLBACK, params={"error": "access_denied"})
    other = await client.get(CALLBACK, params={"error": "server_error"})
    empty = await client.get(CALLBACK)

    assert denied.headers["location"].endswith("?google=denied")
    assert other.headers["location"].endswith("?google=error")
    assert empty.headers["location"].endswith("?google=error")


async def test_access_token_cannot_be_replayed_as_oauth_state_or_the_reverse(make_user, client, google) -> None:
    alice = await make_user()
    state = create_oauth_state(uuid.UUID(alice.user_id), uuid.UUID(alice.workspace_id))

    response = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {state}"})

    assert response.status_code == 401


async def test_disconnect_revokes_at_google_and_forgets_the_tokens(make_user, client, google) -> None:
    alice = await make_user()
    await connect(client, alice)
    [account] = (await accounts(client, alice))["accounts"]

    response = await client.delete(f"{base(alice.workspace_id)}/{account['id']}", headers=alice.headers)

    assert response.status_code == 204
    assert google.revoked == ["refresh-1"]
    assert (await accounts(client, alice))["accounts"] == []
    async with SessionLocal() as session:
        assert await session.scalar(text("SELECT count(*) FROM integration_accounts")) == 0
    again = await client.delete(f"{base(alice.workspace_id)}/{account['id']}", headers=alice.headers)
    assert again.status_code == 404


async def test_disconnect_succeeds_even_if_google_revocation_fails(make_user, client, google) -> None:
    alice = await make_user()
    await connect(client, alice)
    [account] = (await accounts(client, alice))["accounts"]

    async def boom(token: str) -> None:
        raise RuntimeError("network down")

    google.revoke = boom  # type: ignore[method-assign]
    response = await client.delete(f"{base(alice.workspace_id)}/{account['id']}", headers=alice.headers)

    assert response.status_code == 204
    assert (await accounts(client, alice))["accounts"] == []


async def test_connections_are_private(make_user, client, google) -> None:
    alice = await make_user("alice@example.com", "Alice")
    bob = await make_user("bob@example.com", "Bob")
    await connect(client, alice)
    [account] = (await accounts(client, alice))["accounts"]

    assert (await accounts(client, bob))["accounts"] == []
    assert (await client.get(base(alice.workspace_id), headers=bob.headers)).status_code == 404
    assert (
        await client.delete(f"{base(bob.workspace_id)}/{account['id']}", headers=bob.headers)
    ).status_code == 404
    assert (await client.get(f"{base(bob.workspace_id)}/google/calendar/events", headers=bob.headers)).status_code == 409
    assert len((await accounts(client, alice))["accounts"]) == 1


async def test_endpoints_require_authentication(make_user, client, google) -> None:
    alice = await make_user()
    for method, path in [
        ("GET", ""), ("POST", "/google/connect"), ("GET", "/google/gmail/messages"),
        ("GET", "/google/calendar/events"), ("GET", "/google/drive/files"),
    ]:
        response = await client.request(method, base(alice.workspace_id) + path)
        assert response.status_code == 401, path


# --- Reading Google data ----------------------------------------------------------------------


async def test_data_requires_a_connection(make_user, client, google) -> None:
    alice = await make_user()

    for path in ["gmail/messages", "calendar/events", "drive/files"]:
        response = await client.get(f"{base(alice.workspace_id)}/google/{path}", headers=alice.headers)
        assert response.status_code == 409, path
        assert response.json()["error"]["code"] == "GOOGLE_NOT_CONNECTED"


async def test_gmail_search_and_read(make_user, client, google) -> None:
    alice = await make_user()
    await connect(client, alice)
    google.emails = [email("m1", "Proposal feedback", snippet="Looks good"), email("m2", "Lunch?")]
    google.email_bodies["m1"] = "Hi, the proposal looks good to me."
    url = f"{base(alice.workspace_id)}/google/gmail/messages"

    found = await client.get(url, params={"q": "proposal"}, headers=alice.headers)
    one = await client.get(f"{url}/m1", headers=alice.headers)

    assert [m["id"] for m in found.json()] == ["m1"]
    assert found.json()[0]["sender"] == "Ram <ram@abc.test>"
    assert one.json()["body"] == "Hi, the proposal looks good to me."
    assert set(google.tokens_used) == {"access-1"}
    assert (await client.get(f"{url}/missing", headers=alice.headers)).status_code == 404
    assert (await client.get(f"{url}/bad id!", headers=alice.headers)).status_code == 422
    assert (await client.get(url, params={"limit": 99}, headers=alice.headers)).status_code == 422


async def test_calendar_returns_events_and_conflicts(make_user, client, google) -> None:
    alice = await make_user()
    await connect(client, alice)
    google.events = [
        event("a", "Standup", at(9), at(10)),
        event("b", "Review", at(9, 30), at(10, 30)),
        event("c", "Far future", at(9, day=20), at(10, day=20)),
    ]
    url = f"{base(alice.workspace_id)}/google/calendar/events"

    week = (await client.get(url, params={"days": 7}, headers=alice.headers)).json()
    month = (await client.get(url, params={"days": 31}, headers=alice.headers)).json()

    assert [e["id"] for e in week["events"]] == ["a", "b"]
    assert week["conflicts"] == [["a", "b"]]
    assert [e["id"] for e in month["events"]] == ["a", "b", "c"]
    assert (await client.get(url, params={"timezone": "Mars/Base"}, headers=alice.headers)).status_code == 400
    assert (await client.get(url, params={"days": 0}, headers=alice.headers)).status_code == 422
    assert (await client.get(url, params={"timezone": "Asia/Kathmandu"}, headers=alice.headers)).status_code == 200


async def test_drive_search(make_user, client, google) -> None:
    alice = await make_user()
    await connect(client, alice)
    google.files = [
        DriveFile("f1", "Budget 2026", "application/vnd.google-apps.document", at(8), "https://drive/f1"),
        DriveFile("f2", "Holiday photos", "image/jpeg", None, None, 1234),
    ]

    response = await client.get(
        f"{base(alice.workspace_id)}/google/drive/files", params={"q": "budget"}, headers=alice.headers
    )

    assert [f["name"] for f in response.json()] == ["Budget 2026"]
    assert response.json()[0]["link"] == "https://drive/f1"


async def test_drive_import_creates_a_searchable_document(make_user, client, google) -> None:
    alice = await make_user()
    await connect(client, alice)
    google.downloads["f1"] = DriveContent("Budget 2026.txt", b"The quarterly budget covers marketing and travel.")

    response = await client.post(
        f"{base(alice.workspace_id)}/google/drive/files/f1/import", headers=alice.headers
    )

    assert response.status_code == 202, response.text
    document = response.json()
    assert document["filename"] == "Budget 2026.txt" and document["status"] == "pending"
    docs = f"/api/v1/workspaces/{alice.workspace_id}/documents"
    ready = (await client.get(f"{docs}/{document['id']}", headers=alice.headers)).json()
    assert ready["status"] == "ready"
    hits = (await client.get(f"{docs}/search", params={"q": "budget marketing"}, headers=alice.headers)).json()
    assert hits[0]["filename"] == "Budget 2026.txt"


@pytest.mark.parametrize("error,status,code", [
    (UnsupportedDriveFileError(), 422, "GOOGLE_UNSUPPORTED_FILE"),
    (DriveFileTooLargeError(), 413, "GOOGLE_FILE_TOO_LARGE"),
    (GoogleApiError(404, "Google could not find that item."), 404, "GOOGLE_ITEM_NOT_FOUND"),
])
async def test_drive_import_failures_are_reported_clearly(make_user, client, google, error, status, code) -> None:
    alice = await make_user()
    await connect(client, alice)
    google.downloads["f1"] = error

    response = await client.post(
        f"{base(alice.workspace_id)}/google/drive/files/f1/import", headers=alice.headers
    )

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    docs = (await client.get(f"/api/v1/workspaces/{alice.workspace_id}/documents", headers=alice.headers)).json()
    assert docs["total"] == 0


# --- Tokens: refresh, revocation, scopes ----------------------------------------------------


async def expire_token(user_id: str) -> None:
    async with SessionLocal() as session:
        await session.execute(
            text("UPDATE integration_accounts SET token_expires_at = now() - interval '1 minute' WHERE user_id = :u"),
            {"u": user_id},
        )
        await session.commit()


async def test_expired_access_tokens_are_refreshed_transparently(make_user, client, google) -> None:
    alice = await make_user()
    await connect(client, alice)
    google.emails = [email("m1", "Hello")]
    await expire_token(alice.user_id)
    url = f"{base(alice.workspace_id)}/google/gmail/messages"

    first = await client.get(url, headers=alice.headers)
    second = await client.get(url, headers=alice.headers)

    assert first.status_code == 200 and second.status_code == 200
    assert google.refresh_calls == ["refresh-1"]  # refreshed once, then reused
    assert google.tokens_used == ["access-2", "access-2"]


async def test_failed_refresh_marks_the_connection_for_reauthorization(make_user, client, google) -> None:
    alice = await make_user()
    await connect(client, alice)
    await expire_token(alice.user_id)
    google.refresh_error = GoogleAuthError("invalid_grant")
    url = f"{base(alice.workspace_id)}/google/gmail/messages"

    response = await client.get(url, headers=alice.headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "GOOGLE_REAUTH_REQUIRED"
    assert (await accounts(client, alice))["accounts"][0]["status"] == "needs_reauth"
    google.refresh_error = None
    again = await client.get(url, headers=alice.headers)
    assert again.status_code == 409 and google.refresh_calls == ["refresh-1"]  # no pointless retries
    await connect(client, alice)  # reconnecting fixes it
    assert (await accounts(client, alice))["accounts"][0]["status"] == "active"
    assert (await client.get(url, headers=alice.headers)).status_code == 200


async def test_google_rejecting_a_token_mid_use_needs_reauthorization(make_user, client, google) -> None:
    alice = await make_user()
    await connect(client, alice)
    google.data_error = GoogleAuthError("revoked in Google account settings")

    response = await client.get(f"{base(alice.workspace_id)}/google/calendar/events", headers=alice.headers)

    assert response.status_code == 409
    assert (await accounts(client, alice))["accounts"][0]["status"] == "needs_reauth"


async def test_an_unreadable_stored_token_needs_reauthorization(make_user, client, google) -> None:
    alice = await make_user()
    await connect(client, alice)
    async with SessionLocal() as session:
        await session.execute(text("UPDATE integration_accounts SET access_token_encrypted = 'garbage'"))
        await session.commit()

    response = await client.get(f"{base(alice.workspace_id)}/google/drive/files", headers=alice.headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "GOOGLE_REAUTH_REQUIRED"


async def test_only_granted_permissions_are_usable(make_user, client, google) -> None:
    alice = await make_user()
    google.tokens = make_tokens(scopes=[SCOPE_OPENID, SCOPE_EMAIL, SCOPE_CALENDAR])
    await connect(client, alice)
    root = f"{base(alice.workspace_id)}/google"

    mail = await client.get(f"{root}/gmail/messages", headers=alice.headers)
    cal = await client.get(f"{root}/calendar/events", headers=alice.headers)

    assert mail.status_code == 409 and mail.json()["error"]["code"] == "GOOGLE_SCOPE_MISSING"
    assert cal.status_code == 200
    [account] = (await accounts(client, alice))["accounts"]
    assert (account["gmail"], account["calendar"], account["drive"]) == (False, True, False)


@pytest.mark.parametrize("status,expected", [(500, 502), (503, 502), (429, 429)])
async def test_google_outages_are_reported_without_leaking_details(make_user, client, google, status, expected) -> None:
    alice = await make_user()
    await connect(client, alice)
    google.data_error = GoogleApiError(status)

    response = await client.get(f"{base(alice.workspace_id)}/google/gmail/messages", headers=alice.headers)

    assert response.status_code == expected
    assert "Traceback" not in response.text


# --- Assistant tools ----------------------------------------------------------------------------


async def chat(client: AsyncClient, user, message: str) -> dict:
    response = await client.post(
        f"/api/v1/workspaces/{user.workspace_id}/assistant/chat",
        json={"message": message, "timezone": "UTC"},
        headers=user.headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["message"]


async def test_assistant_reads_the_calendar_and_flags_clashes(make_user, client, google) -> None:
    alice = await make_user()
    await connect(client, alice)
    google.events = [event("a", "Standup", at(9), at(10)), event("b", "Review", at(9, 30), at(10, 30))]

    reply = await chat(client, alice, "What is on my calendar today?")

    assert reply["tool_events"][0]["name"] == "get_calendar" and reply["tool_events"][0]["ok"]
    assert "Standup" in reply["content"] and "Review" in reply["content"]
    assert "overlap" in reply["content"]


async def test_assistant_searches_email_and_drive(make_user, client, google) -> None:
    alice = await make_user()
    await connect(client, alice)
    google.emails = [email("m1", "Invoice 42", sender="billing@shop.test")]
    google.files = [DriveFile("f1", "Invoice template", "text/plain", None, None)]

    mail = await chat(client, alice, "Search my email for invoice")
    drive = await chat(client, alice, "Search my drive for invoice")

    assert "Invoice 42" in mail["content"] and "billing@shop.test" in mail["content"]
    assert "Invoice template" in drive["content"]


async def test_assistant_explains_when_google_is_not_connected(make_user, client, google) -> None:
    alice = await make_user()

    reply = await chat(client, alice, "Check my email for invoices")

    assert reply["tool_events"][0]["ok"] is False
    assert "isn't connected" in reply["content"]


async def test_assistant_google_tools_use_the_callers_own_connection(make_user, client, google) -> None:
    alice = await make_user("alice@example.com", "Alice")
    bob = await make_user("bob@example.com", "Bob")
    await connect(client, alice)
    google.emails = [email("m1", "Alice secret plans")]

    mine = await chat(client, alice, "Search my email for secret")
    theirs = await chat(client, bob, "Search my email for secret")

    assert "Alice secret plans" in mine["content"]
    assert theirs["tool_events"][0]["ok"] is False
    assert "Alice secret plans" not in theirs["content"]


async def test_reminding_to_email_is_still_a_task_not_an_email_search(make_user, client, google) -> None:
    alice = await make_user()
    await connect(client, alice)

    reply = await chat(client, alice, "Remind me to email Ram tomorrow")

    assert reply["tool_events"][0]["name"] == "create_task"


async def test_long_emails_are_truncated_before_reaching_the_assistant(make_user, client, google) -> None:
    from app.tools.google_tools import MAX_EMAIL_CHARS

    alice = await make_user()
    await connect(client, alice)
    google.emails = [email("m1", "Newsletter")]
    google.email_bodies["m1"] = "x" * 50_000

    from app.tools import default_registry
    from app.tools.base import ToolContext
    from zoneinfo import ZoneInfo
    import json

    async with SessionLocal() as session:
        ctx = ToolContext(
            session=session, workspace_id=uuid.UUID(alice.workspace_id), user_id=uuid.UUID(alice.user_id),
            timezone=ZoneInfo("UTC"), google=google,
        )
        outcome = await default_registry().execute("read_email", {"message_id": "m1"}, ctx)

    body = json.loads(outcome.content)["email"]["body"]
    assert len(body) == MAX_EMAIL_CHARS
