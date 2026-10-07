from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import text

from app.db.session import SessionLocal
from app.integrations.google.types import AwaitingReply, GoogleApiError
from tests.test_documents import upload
from tests.test_integrations import at, connect, event
from tests.test_memories import add as add_memory
from tests.test_notes import create_note
from tests.test_tasks import create_task, iso


def brief_url(workspace_id: str) -> str:
    return f"/api/v1/workspaces/{workspace_id}/briefing"


async def briefing(client: AsyncClient, user, expect: int = 200, **params) -> dict:
    response = await client.get(brief_url(user.workspace_id), params=params, headers=user.headers)
    assert response.status_code == expect, response.text
    return response.json()


def end_of_today() -> str:
    return datetime.now(UTC).replace(hour=23, minute=59, second=59, microsecond=0).isoformat()


def end_of_tomorrow() -> str:
    return (datetime.now(UTC) + timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0).isoformat()


def titles(items: list[dict]) -> list[str]:
    return [i["title"] for i in items]


# --- Tasks ---------------------------------------------------------------------------------


async def test_an_empty_workspace_gets_an_empty_but_valid_briefing(make_user, client) -> None:
    alice = await make_user()

    body = await briefing(client, alice)

    assert body["priorities"] == [] and body["overdue"] == [] and body["due_today"] == []
    assert body["meetings"] == [] and body["meetings_status"] == "not_connected"
    assert body["follow_ups"] == [] and body["follow_ups_status"] == "not_connected"
    assert body["pending_suggestions"] == 0 and body["suggested_actions"] == []
    assert body["timezone"] == "UTC"
    assert body["date"] == datetime.now(UTC).date().isoformat()


async def test_tasks_are_sorted_into_overdue_today_and_tomorrow(make_user, client) -> None:
    alice = await make_user()
    await create_task(client, alice, title="Late report", due_date=iso(-timedelta(days=3)), priority="high")
    await create_task(client, alice, title="Send invoice", due_date=end_of_today())
    await create_task(client, alice, title="Prep slides", due_date=end_of_tomorrow())
    await create_task(client, alice, title="Done already", due_date=iso(-timedelta(days=1)), status="completed")
    await create_task(client, alice, title="Whenever")

    body = await briefing(client, alice)

    assert titles(body["overdue"]) == ["Late report"]
    assert titles(body["due_today"]) == ["Send invoice"]
    assert titles(body["due_tomorrow"]) == ["Prep slides"]
    first = body["priorities"][0]
    assert first["title"] == "Late report"
    assert first["reason"] == "Overdue by 3 days · High priority"
    assert "Done already" not in titles(body["priorities"]) and "Whenever" not in titles(body["priorities"])
    assert any("Clear or reschedule 1 overdue task" in a and "Late report" in a for a in body["suggested_actions"])


async def test_at_most_five_priorities_are_returned(make_user, client) -> None:
    alice = await make_user()
    for i in range(8):
        await create_task(client, alice, title=f"Urgent {i}", priority="urgent")

    body = await briefing(client, alice)

    assert len(body["priorities"]) == 5


async def test_timezone_parameter_is_validated(make_user, client) -> None:
    alice = await make_user()

    assert (await briefing(client, alice, expect=400, timezone="Mars/Base"))["error"]["code"] == "BAD_REQUEST"
    assert (await briefing(client, alice, timezone="Asia/Kathmandu"))["timezone"] == "Asia/Kathmandu"


async def test_documents_changed_recently_are_listed(make_user, client) -> None:
    alice = await make_user()
    await upload(client, alice, "fresh.txt", b"new numbers for the quarter")
    old = await upload(client, alice, "stale.txt", b"old numbers")
    async with SessionLocal() as session:
        await session.execute(
            text("UPDATE documents SET processed_at = now() - interval '10 days', created_at = now() - interval '10 days' WHERE id = :id"),
            {"id": old["id"]},
        )
        await session.commit()

    body = await briefing(client, alice)

    assert [d["filename"] for d in body["recent_documents"]] == ["fresh.txt"]


# --- Follow-ups -------------------------------------------------------------------------------


async def test_stale_tasks_and_commitments_become_follow_ups(make_user, client) -> None:
    alice = await make_user()
    stale = await create_task(client, alice, title="Chase the vendor", status="in_progress")
    await create_task(client, alice, title="Fresh task", status="in_progress")
    await create_task(client, alice, title="Old but unimportant", priority="low")
    await add_memory(client, alice, "I promised Priya the pricing sheet", kind="commitment", subject="Priya")
    await add_memory(client, alice, "Ram likes tea", kind="preference")
    async with SessionLocal() as session:
        await session.execute(
            text("UPDATE tasks SET updated_at = now() - interval '10 days' WHERE id = :id OR title = 'Old but unimportant'"),
            {"id": stale["id"]},
        )
        await session.commit()

    body = await briefing(client, alice)

    by_kind = {f["kind"]: f for f in body["follow_ups"]}
    assert set(by_kind) == {"task", "commitment"}
    assert by_kind["task"]["title"] == "Chase the vendor" and by_kind["task"]["days_waiting"] >= 10
    assert by_kind["commitment"]["title"] == "I promised Priya the pricing sheet"
    assert by_kind["commitment"]["detail"] == "Priya"


# --- With Google connected -----------------------------------------------------------------


async def test_meetings_come_with_conflicts_and_your_own_context(make_user, client, google) -> None:
    alice = await make_user()
    await connect(client, alice)
    await upload(client, alice, "revenue.txt", b"Quarterly revenue review: revenue grew in the sales segment.")
    await create_note(client, alice, title="Sales meeting agenda", content="topics for the sales meeting")
    await add_memory(client, alice, "Priya leads the sales meeting each quarter", kind="person", subject="Priya")
    await create_task(client, alice, title="Prepare sales meeting deck")
    await create_task(client, alice, title="Sales meeting deck (done)", status="completed")
    google.events = [
        event("e1", "Sales meeting", at(9), at(10), attendees=["priya@x.test"]),
        event("e2", "Dentist", at(9, 30), at(10, 30)),
        event("e3", "Team lunch", at(12), at(13)),
        event("e4", "Company holiday", at(0), at(23, 59), all_day=True),
        event("e5", "Skipped sync", at(15), at(16), declined=True),
    ]
    google.events = [e for e in google.events if e.start.date() == datetime.now(UTC).date()]

    body = await briefing(client, alice)

    assert body["meetings_status"] == "ok"
    meetings = {m["id"]: m for m in body["meetings"]}
    assert set(meetings) == {"e1", "e2", "e3", "e4", "e5"}
    assert meetings["e1"]["overlaps"] and meetings["e2"]["overlaps"]
    assert not meetings["e3"]["overlaps"] and not meetings["e4"]["overlaps"]
    context = {(c["type"], c["title"]) for c in meetings["e1"]["context"]}
    assert ("note", "Sales meeting agenda") in context
    assert ("task", "Prepare sales meeting deck") in context
    assert ("task", "Sales meeting deck (done)") not in context  # finished tasks aren't context
    assert meetings["e4"]["context"] == [] and meetings["e5"]["context"] == []
    assert any("Resolve the overlap between “Sales meeting” and “Dentist”" in a for a in body["suggested_actions"])
    assert any("Review “Sales meeting agenda” before “Sales meeting”" in a for a in body["suggested_actions"])


async def test_event_titles_are_searched_as_plain_words_not_as_search_commands(make_user, client, google) -> None:
    alice = await make_user()
    await connect(client, alice)
    await create_task(client, alice, title="Fix budget", due_date=iso(-timedelta(days=2)))
    await create_note(client, alice, title="Home", tags=["work"])
    google.events = [event("e1", "is:overdue tag:work", at(11), at(12))]

    body = await briefing(client, alice)

    assert body["meetings"][0]["context"] == []  # a hostile title can't pull in unrelated data


async def test_email_follow_ups_appear_when_gmail_is_connected(make_user, client, google) -> None:
    alice = await make_user()
    await connect(client, alice)
    google.awaiting = [
        AwaitingReply("t1", "Proposal for ABC", "Ram Sharma <ram@abc.test>, Sita <sita@abc.test>", at(9), 6),
        AwaitingReply("t2", "Too fresh", "x@y.test", at(9), 1),  # under the 3-day minimum: not returned
    ]

    body = await briefing(client, alice)

    assert body["follow_ups_status"] == "ok"
    [item] = [f for f in body["follow_ups"] if f["kind"] == "email"]
    assert item["title"] == "No reply from Ram Sharma"
    assert item["detail"] == "Proposal for ABC" and item["days_waiting"] == 6
    assert any("Follow up: no reply from ram sharma about “Proposal for ABC” (6 days)" in a for a in body["suggested_actions"])


async def test_google_problems_never_break_the_briefing(make_user, client, google) -> None:
    alice = await make_user()
    await create_task(client, alice, title="Still shown", due_date=end_of_today())
    await connect(client, alice)

    google.data_error = GoogleApiError(500)
    down = await briefing(client, alice)
    async with SessionLocal() as session:
        await session.execute(text("UPDATE integration_accounts SET status = 'needs_reauth'"))
        await session.commit()
    expired = await briefing(client, alice)

    assert down["meetings_status"] == "unavailable" and down["follow_ups_status"] == "unavailable"
    assert expired["meetings_status"] == "needs_reauth" and expired["follow_ups_status"] == "needs_reauth"
    for body in (down, expired):
        assert titles(body["due_today"]) == ["Still shown"]  # the non-Google parts still work


async def test_missing_calendar_permission_is_reported_as_not_connected(make_user, client, google) -> None:
    from app.integrations.google.types import SCOPE_GMAIL
    from tests.fakes import make_tokens

    alice = await make_user()
    google.tokens = make_tokens(scopes=[SCOPE_GMAIL])
    await connect(client, alice)

    body = await briefing(client, alice)

    assert body["meetings_status"] == "not_connected"
    assert body["follow_ups_status"] == "ok"


# --- Access control, assistant ---------------------------------------------------------------


async def test_briefings_are_private_to_their_workspace(make_user, client) -> None:
    alice = await make_user("alice@example.com", "Alice")
    bob = await make_user("bob@example.com", "Bob")
    await create_task(client, alice, title="Alice secret", due_date=end_of_today())

    mine = await briefing(client, alice)
    theirs = await briefing(client, bob)

    assert titles(mine["due_today"]) == ["Alice secret"]
    assert theirs["due_today"] == [] and "Alice secret" not in str(theirs)
    assert (await client.get(brief_url(alice.workspace_id), headers=bob.headers)).status_code == 404
    assert (await client.get(brief_url(alice.workspace_id))).status_code == 401


async def test_the_assistant_can_prepare_you_for_today(make_user, client) -> None:
    alice = await make_user()
    await create_task(client, alice, title="Send invoice", due_date=end_of_today(), priority="high")

    response = await client.post(
        f"/api/v1/workspaces/{alice.workspace_id}/assistant/chat",
        json={"message": "Prepare me for today", "timezone": "UTC"},
        headers=alice.headers,
    )

    assert response.status_code == 200
    message = response.json()["message"]
    assert message["tool_events"][0]["name"] == "get_briefing" and message["tool_events"][0]["ok"]
    assert "Send invoice" in message["content"] and "Due today" in message["content"]
    assert "Google isn't connected" in message["content"]


async def test_asking_for_a_briefing_in_a_task_request_still_creates_the_task(make_user, client) -> None:
    alice = await make_user()

    response = await client.post(
        f"/api/v1/workspaces/{alice.workspace_id}/assistant/chat",
        json={"message": "Create a task to write the briefing tomorrow", "timezone": "UTC"},
        headers=alice.headers,
    )

    assert response.json()["message"]["tool_events"][0]["name"] == "create_task"
