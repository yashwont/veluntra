"""GOOGLE_PROVIDER=demo: the app works end to end with canned data and no credentials."""

from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.integrations.google.demo import DEMO_EMAIL, DemoGoogleApi
from app.integrations.google.factory import get_google_api
from app.integrations.google.types import GoogleApiError, GoogleAuthError
from app.main import app
from tests.test_documents import upload  # noqa: F401  (keeps fixtures consistent)


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.setattr(get_settings(), "google_provider", "demo")
    app.dependency_overrides[get_google_api] = lambda: DemoGoogleApi()
    yield
    app.dependency_overrides.pop(get_google_api, None)


def base(workspace_id: str) -> str:
    return f"/api/v1/workspaces/{workspace_id}"


async def connect_demo(client: AsyncClient, user) -> None:
    started = await client.post(f"{base(user.workspace_id)}/integrations/google/connect", headers=user.headers)
    assert started.status_code == 200, started.text
    url = urlparse(started.json()["authorization_url"])
    # the demo "consent screen" is the app's own callback, answered immediately
    assert url.path == "/api/v1/integrations/google/callback"
    params = {k: v[0] for k, v in parse_qs(url.query).items()}
    response = await client.get(url.path, params=params)
    assert response.headers["location"].endswith("?google=connected")


def test_the_factory_serves_the_demo_client_only_in_demo_mode(monkeypatch) -> None:
    get_google_api.cache_clear()
    try:
        monkeypatch.setattr(get_settings(), "google_provider", "demo")
        assert isinstance(get_google_api(), DemoGoogleApi)
        get_google_api.cache_clear()
        monkeypatch.setattr(get_settings(), "google_provider", "real")
        assert not isinstance(get_google_api(), DemoGoogleApi)
    finally:
        get_google_api.cache_clear()


def test_demo_mode_counts_as_configured_without_credentials(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "google_client_id", "")
    monkeypatch.setattr(settings, "google_client_secret", "")
    assert settings.google_configured is False
    monkeypatch.setattr(settings, "google_provider", "demo")
    assert settings.google_configured is True and settings.google_demo is True


async def test_demo_codes_are_exact(demo) -> None:
    api = DemoGoogleApi()

    with pytest.raises(GoogleAuthError):
        await api.exchange_code("anything-else")
    assert (await api.exchange_code("demo")).email == DEMO_EMAIL
    with pytest.raises(GoogleApiError):
        await api.gmail_get("t", "missing")


async def test_connecting_in_demo_mode_works_with_no_credentials(make_user, client, demo) -> None:
    alice = await make_user()

    before = (await client.get(f"{base(alice.workspace_id)}/integrations", headers=alice.headers)).json()
    await connect_demo(client, alice)
    after = (await client.get(f"{base(alice.workspace_id)}/integrations", headers=alice.headers)).json()

    assert before["demo"] is True and before["google_configured"] is True and before["accounts"] == []
    [account] = after["accounts"]
    assert account["account_email"] == DEMO_EMAIL
    assert account["gmail"] and account["calendar"] and account["drive"]


async def test_demo_calendar_has_a_clash_and_the_briefing_shows_it(make_user, client, demo) -> None:
    alice = await make_user()
    await connect_demo(client, alice)

    calendar = (await client.get(f"{base(alice.workspace_id)}/integrations/google/calendar/events", headers=alice.headers)).json()
    briefing = (await client.get(f"{base(alice.workspace_id)}/briefing", headers=alice.headers)).json()

    assert ["demo-e2", "demo-e3"] in calendar["conflicts"]  # client call overlaps proposal review
    clashing = {m["title"] for m in briefing["meetings"] if m["overlaps"]}
    assert clashing == {"Client call - ABC Traders", "Proposal review"}
    assert briefing["meetings_status"] == "ok" and briefing["follow_ups_status"] == "ok"
    emails = [f for f in briefing["follow_ups"] if f["kind"] == "email"]
    assert {e["detail"] for e in emails} == {"Partnership proposal", "Re: Website redesign quote"}


async def test_scanning_demo_mail_finds_real_requests_and_ignores_the_rest(make_user, client, demo) -> None:
    alice = await make_user()
    await connect_demo(client, alice)

    response = await client.post(f"{base(alice.workspace_id)}/suggestions/scan", headers=alice.headers)

    assert response.status_code == 200, response.text
    result = response.json()
    labels = {s["source_label"] for s in result["pending"]}
    assert labels == {
        "Proposal feedback", "Invoice 1042 is overdue", "Quarterly revenue review - agenda",  # requests
        "Partnership proposal", "Website redesign quote",  # nobody replied
    }
    assert result["created"] == 5
    assert "Dev Weekly #212" not in labels and "Photos from the trip" not in labels
    ram = next(s for s in result["pending"] if s["source_label"] == "Proposal feedback")
    assert ram["due_date"] is not None and ram["priority"] == "high"  # "by Friday", within reach or urgent


async def test_demo_email_drive_and_import(make_user, client, demo) -> None:
    alice = await make_user()
    await connect_demo(client, alice)
    root = f"{base(alice.workspace_id)}/integrations/google"

    mail = (await client.get(f"{root}/gmail/messages", params={"q": "invoice"}, headers=alice.headers)).json()
    body = (await client.get(f"{root}/gmail/messages/demo-m1", headers=alice.headers)).json()
    files = (await client.get(f"{root}/drive/files", params={"q": "pricing"}, headers=alice.headers)).json()
    photos = await client.post(f"{root}/drive/files/demo-f3/import", headers=alice.headers)
    imported = await client.post(f"{root}/drive/files/demo-f2/import", headers=alice.headers)

    assert [m["id"] for m in mail] == ["demo-m2"]
    assert "revised pricing" in body["body"]
    assert [f["name"] for f in files] == ["ABC Traders pricing sheet"]
    assert photos.status_code == 422  # an image can't become a document
    assert imported.status_code == 202
    docs = f"{base(alice.workspace_id)}/documents"
    ready = (await client.get(f"{docs}/{imported.json()['id']}", headers=alice.headers)).json()
    assert ready["status"] == "ready"
    hits = (await client.get(f"{docs}/search", params={"q": "volume tier units"}, headers=alice.headers)).json()
    assert hits and hits[0]["filename"] == "ABC Traders pricing sheet.txt"


async def test_the_assistant_works_against_demo_google(make_user, client, demo) -> None:
    alice = await make_user()
    await connect_demo(client, alice)

    reply = await client.post(
        f"{base(alice.workspace_id)}/assistant/chat",
        json={"message": "What is on my calendar today?", "timezone": "UTC"},
        headers=alice.headers,
    )

    content = reply.json()["message"]["content"]
    assert "Sales standup" in content and "overlap" in content
