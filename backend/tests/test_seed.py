"""The demo seed script: what a fresh install gets."""

from httpx import AsyncClient
from sqlalchemy import text

from app.db.session import SessionLocal
from scripts.seed_demo import DEMO_EMAIL, DEMO_PASSWORD, seed


async def sign_in(client: AsyncClient) -> dict[str, str]:
    login = await client.post("/api/v1/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def workspace_url(client: AsyncClient, headers) -> str:
    [workspace] = (await client.get("/api/v1/workspaces", headers=headers)).json()
    return f"/api/v1/workspaces/{workspace['id']}"


async def test_seeding_creates_a_demo_account_with_realistic_content(client, capsys) -> None:
    await seed()
    headers = await sign_in(client)
    ws = await workspace_url(client, headers)

    tasks = (await client.get(f"{ws}/tasks", params={"limit": 100}, headers=headers)).json()
    notes = (await client.get(f"{ws}/notes", headers=headers)).json()
    documents = (await client.get(f"{ws}/documents", headers=headers)).json()
    memories = (await client.get(f"{ws}/memories", headers=headers)).json()
    conversations = (await client.get(f"{ws}/conversations", headers=headers)).json()

    assert tasks["total"] >= 8
    assert {"assistant", "manual"} <= {t["source"] for t in tasks["items"]}  # one was made by the chat
    assert notes["total"] == 4
    assert documents["total"] == 3 and all(d["status"] == "ready" for d in documents["items"])
    assert memories["total"] == 5
    assert {"conversation", "manual"} == {m["source_type"] for m in memories["items"]}
    assert conversations["total"] == 1
    assert DEMO_EMAIL in capsys.readouterr().out


async def test_the_seeded_account_makes_a_meaningful_briefing_and_search(client) -> None:
    await seed()
    headers = await sign_in(client)
    ws = await workspace_url(client, headers)

    briefing = (await client.get(f"{ws}/briefing", headers=headers)).json()
    found = (await client.get(f"{ws}/search", params={"q": "ABC Traders"}, headers=headers)).json()

    assert briefing["overdue"][0]["title"] == "Pay cloud hosting invoice 1042"
    assert briefing["priorities"][0]["reason"].startswith("Overdue by 2 days")
    assert any(f["kind"] == "task" and f["title"] == "Review hiring plan" for f in briefing["follow_ups"])
    assert any(f["kind"] == "commitment" for f in briefing["follow_ups"])
    assert {r["type"] for r in found["results"]} >= {"note", "document", "memory"}


async def test_seeding_twice_changes_nothing(client, capsys) -> None:
    await seed()
    capsys.readouterr()

    await seed()

    assert "already exists" in capsys.readouterr().out
    async with SessionLocal() as session:
        assert await session.scalar(text("SELECT count(*) FROM users")) == 1
        assert await session.scalar(text("SELECT count(*) FROM notes")) == 4
