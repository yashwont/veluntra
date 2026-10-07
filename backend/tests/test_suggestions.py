from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import text

from app.db.session import SessionLocal
from app.integrations.google.types import AwaitingReply, EmailSummary
from tests.test_integrations import at, connect


def base(workspace_id: str) -> str:
    return f"/api/v1/workspaces/{workspace_id}/suggestions"


def mail(id: str, subject: str, snippet: str = "", sender: str = "Ram Sharma <ram@abc.test>") -> EmailSummary:
    return EmailSummary(id=id, thread_id="t-" + id, sender=sender, subject=subject, date=at(9), snippet=snippet)


async def scan(client: AsyncClient, user, expect: int = 200, **params) -> dict:
    response = await client.post(f"{base(user.workspace_id)}/scan", params=params, headers=user.headers)
    assert response.status_code == expect, response.text
    return response.json()


async def pending(client: AsyncClient, user, **params) -> list[dict]:
    response = await client.get(base(user.workspace_id), params=params, headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


async def tasks_of(client: AsyncClient, user) -> dict:
    return (await client.get(f"/api/v1/workspaces/{user.workspace_id}/tasks", headers=user.headers)).json()


def seed(google) -> None:
    google.emails = [
        mail("m1", "Contract review", "Can you send me your comments by Friday?"),
        mail("m2", "Weekly digest", "Please read our newsletter", sender="News <newsletter@site.test>"),
        mail("m3", "Lunch on Friday?", "Fancy trying the new place?"),
        mail("m4", "Invoice 77", "Your invoice is overdue, payment pending.", sender="Billing <billing@shop.test>"),
        mail("m5", "Note to self", "Please remember to review this", sender="Me <me@gmail.test>"),  # own address
    ]
    google.awaiting = [AwaitingReply("th1", "Re: Proposal for ABC", "Sita <sita@abc.test>", at(9), 8)]


def matches_query(google) -> None:
    """The fake only returns emails whose text contains the query; the scan query is
    an operator string, so make the fake return everything for it."""

    original = google.gmail_search

    async def everything(access_token, query, limit):
        google._use(access_token)
        return google.emails[:limit]

    google.gmail_search = everything  # type: ignore[method-assign]
    _ = original


# --- Scanning -------------------------------------------------------------------------------


async def test_scanning_needs_a_google_connection(make_user, client, google) -> None:
    alice = await make_user()

    body = await scan(client, alice, expect=409)

    assert body["error"]["code"] == "GOOGLE_NOT_CONNECTED"


async def test_scan_proposes_tasks_only_for_things_that_need_doing(make_user, client, google) -> None:
    alice = await make_user()
    await connect(client, alice)
    seed(google)
    matches_query(google)

    result = await scan(client, alice)

    assert result["created"] == 3  # two requests and one follow-up
    by_label = {s["source_label"]: s for s in result["pending"]}
    assert set(by_label) == {"Contract review", "Invoice 77", "Proposal for ABC"}
    contract = by_label["Contract review"]
    assert contract["kind"] == "email_action"
    assert contract["title"] == "Reply to Ram Sharma: Contract review"
    assert contract["status"] == "pending" and contract["task_id"] is None
    assert contract["due_date"] is not None and contract["priority"] in ("high", "medium")
    assert contract["confidence"] >= 0.6 and "asks you to do something" in contract["reason"]
    assert by_label["Invoice 77"]["priority"] == "high"
    follow_up = by_label["Proposal for ABC"]
    assert follow_up["kind"] == "email_follow_up"
    assert follow_up["title"] == "Follow up: Proposal for ABC"  # "Re:" removed
    assert follow_up["priority"] == "high"  # waited 8 days
    assert "8 days ago" in follow_up["reason"]


async def test_a_scan_never_creates_tasks_by_itself(make_user, client, google) -> None:
    alice = await make_user()
    await connect(client, alice)
    seed(google)
    matches_query(google)

    await scan(client, alice)

    assert (await tasks_of(client, alice))["total"] == 0


async def test_rescanning_does_not_duplicate_suggestions(make_user, client, google) -> None:
    alice = await make_user()
    await connect(client, alice)
    seed(google)
    matches_query(google)
    first = await scan(client, alice)

    second = await scan(client, alice)

    assert first["created"] == 3 and second["created"] == 0
    assert len(second["pending"]) == 3
    google.emails.append(mail("m9", "Budget approval", "Please approve the attached budget"))
    third = await scan(client, alice)
    assert third["created"] == 1 and len(third["pending"]) == 4


async def test_a_dismissed_suggestion_is_not_brought_back_by_the_next_scan(make_user, client, google) -> None:
    alice = await make_user()
    await connect(client, alice)
    seed(google)
    matches_query(google)
    items = (await scan(client, alice))["pending"]
    target = next(s for s in items if s["source_label"] == "Invoice 77")
    await client.post(f"{base(alice.workspace_id)}/{target['id']}/dismiss", headers=alice.headers)

    again = await scan(client, alice)

    assert again["created"] == 0
    assert "Invoice 77" not in [s["source_label"] for s in again["pending"]]


async def test_scan_uses_the_timezone_for_deadlines(make_user, client, google) -> None:
    alice = await make_user()
    await connect(client, alice)
    google.emails = [mail("m1", "Report", "Please send the report by tomorrow")]
    matches_query(google)
    google.awaiting = []

    result = await scan(client, alice, timezone="Asia/Kathmandu")

    due = datetime.fromisoformat(result["pending"][0]["due_date"])
    assert due.utcoffset() is not None
    local_due = due.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Kathmandu"))
    assert (local_due.hour, local_due.minute) == (23, 59)
    assert local_due.date() == (datetime.now(__import__("zoneinfo").ZoneInfo("Asia/Kathmandu")) + timedelta(days=1)).date()
    assert (await scan(client, alice, expect=400, timezone="Mars/Base"))["error"]["code"] == "BAD_REQUEST"


# --- Accepting and dismissing -------------------------------------------------------------------


async def first_suggestion(client, user, google) -> dict:
    await connect(client, user)
    seed(google)
    matches_query(google)
    return next(s for s in (await scan(client, user))["pending"] if s["source_label"] == "Contract review")


async def test_accepting_creates_a_task_from_the_suggestion(make_user, client, google) -> None:
    alice = await make_user()
    suggestion = await first_suggestion(client, alice, google)

    response = await client.post(f"{base(alice.workspace_id)}/{suggestion['id']}/accept", headers=alice.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    task = body["task"]
    assert task["title"] == suggestion["title"]
    assert task["priority"] == suggestion["priority"]
    assert task["due_date"] == suggestion["due_date"]
    assert task["source"] == "suggestion" and task["status"] == "todo"
    assert body["suggestion"]["status"] == "accepted" and body["suggestion"]["task_id"] == task["id"]
    assert (await tasks_of(client, alice))["total"] == 1
    assert all(s["id"] != suggestion["id"] for s in await pending(client, alice))
    accepted = await pending(client, alice, status="accepted")
    assert [s["id"] for s in accepted] == [suggestion["id"]]


async def test_accepting_can_adjust_the_task(make_user, client, google) -> None:
    alice = await make_user()
    suggestion = await first_suggestion(client, alice, google)
    due = (datetime.now(UTC) + timedelta(days=9)).replace(microsecond=0).isoformat()

    response = await client.post(
        f"{base(alice.workspace_id)}/{suggestion['id']}/accept",
        json={"title": "Send contract comments", "priority": "low", "due_date": due},
        headers=alice.headers,
    )

    task = response.json()["task"]
    assert task["title"] == "Send contract comments" and task["priority"] == "low"
    assert datetime.fromisoformat(task["due_date"]) == datetime.fromisoformat(due)


async def test_accepting_can_clear_the_deadline(make_user, client, google) -> None:
    alice = await make_user()
    suggestion = await first_suggestion(client, alice, google)

    response = await client.post(
        f"{base(alice.workspace_id)}/{suggestion['id']}/accept", json={"due_date": None}, headers=alice.headers
    )

    assert response.json()["task"]["due_date"] is None


async def test_invalid_adjustments_are_rejected_and_change_nothing(make_user, client, google) -> None:
    alice = await make_user()
    suggestion = await first_suggestion(client, alice, google)
    url = f"{base(alice.workspace_id)}/{suggestion['id']}/accept"

    for bad in [{"title": ""}, {"priority": "whenever"}, {"due_date": "2026-10-05T09:00:00"}]:
        assert (await client.post(url, json=bad, headers=alice.headers)).status_code == 422, bad

    assert (await tasks_of(client, alice))["total"] == 0
    assert any(s["id"] == suggestion["id"] for s in await pending(client, alice))


async def test_a_suggestion_can_only_be_decided_once(make_user, client, google) -> None:
    alice = await make_user()
    suggestion = await first_suggestion(client, alice, google)
    accept = f"{base(alice.workspace_id)}/{suggestion['id']}/accept"
    dismiss = f"{base(alice.workspace_id)}/{suggestion['id']}/dismiss"
    await client.post(accept, headers=alice.headers)

    again = await client.post(accept, headers=alice.headers)
    dismissed_after = await client.post(dismiss, headers=alice.headers)

    assert again.status_code == 409 and again.json()["error"]["code"] == "SUGGESTION_NOT_PENDING"
    assert dismissed_after.status_code == 409
    assert (await tasks_of(client, alice))["total"] == 1  # accepting twice didn't create a second task


async def test_dismissing_keeps_it_out_of_the_pending_list(make_user, client, google) -> None:
    alice = await make_user()
    suggestion = await first_suggestion(client, alice, google)

    response = await client.post(f"{base(alice.workspace_id)}/{suggestion['id']}/dismiss", headers=alice.headers)

    assert response.status_code == 200 and response.json()["status"] == "dismissed"
    assert all(s["id"] != suggestion["id"] for s in await pending(client, alice))
    assert [s["id"] for s in await pending(client, alice, status="dismissed")] == [suggestion["id"]]
    assert (await client.post(f"{base(alice.workspace_id)}/{suggestion['id']}/accept", headers=alice.headers)).status_code == 409
    assert (await tasks_of(client, alice))["total"] == 0


async def test_deleting_the_task_leaves_the_suggestion_history(make_user, client, google) -> None:
    alice = await make_user()
    suggestion = await first_suggestion(client, alice, google)
    task = (await client.post(f"{base(alice.workspace_id)}/{suggestion['id']}/accept", headers=alice.headers)).json()["task"]

    await client.delete(f"/api/v1/workspaces/{alice.workspace_id}/tasks/{task['id']}", headers=alice.headers)

    [kept] = await pending(client, alice, status="accepted")
    assert kept["status"] == "accepted" and kept["task_id"] is None


# --- Access control --------------------------------------------------------------------------------


async def test_suggestions_are_private_to_their_owner(make_user, client, google) -> None:
    alice = await make_user("alice@example.com", "Alice")
    bob = await make_user("bob@example.com", "Bob")
    suggestion = await first_suggestion(client, alice, google)
    bobs = base(bob.workspace_id)

    assert await pending(client, bob) == []
    assert (await client.post(f"{bobs}/{suggestion['id']}/accept", headers=bob.headers)).status_code == 404
    assert (await client.post(f"{bobs}/{suggestion['id']}/dismiss", headers=bob.headers)).status_code == 404
    assert (await client.get(base(alice.workspace_id), headers=bob.headers)).status_code == 404
    assert (await client.post(f"{base(alice.workspace_id)}/{suggestion['id']}/accept", headers=bob.headers)).status_code == 404
    assert len(await pending(client, alice)) == 3


async def test_endpoints_require_authentication(make_user, client, google) -> None:
    alice = await make_user()
    url = base(alice.workspace_id)

    assert (await client.get(url)).status_code == 401
    assert (await client.post(f"{url}/scan")).status_code == 401


async def test_pending_suggestions_are_counted_in_the_briefing(make_user, client, google) -> None:
    alice = await make_user()
    await first_suggestion(client, alice, google)

    briefing = (await client.get(f"/api/v1/workspaces/{alice.workspace_id}/briefing", headers=alice.headers)).json()

    assert briefing["pending_suggestions"] == 3
    assert any("Review 3 suggested tasks" in a for a in briefing["suggested_actions"])


async def test_a_concurrent_duplicate_insert_is_ignored_not_a_crash(make_user, client, google) -> None:
    alice = await make_user()
    suggestion = await first_suggestion(client, alice, google)
    from app.models.suggestion import Suggestion, SuggestionKind
    import uuid

    from app.services.suggestion_service import SuggestionService

    async with SessionLocal() as session:
        service = SuggestionService(session, uuid.UUID(alice.workspace_id), uuid.UUID(alice.user_id), google)
        duplicate = Suggestion(
            workspace_id=uuid.UUID(alice.workspace_id), user_id=uuid.UUID(alice.user_id),
            kind=SuggestionKind.EMAIL_ACTION, title="dup", reason="r", source_type="email", source_id="m1",
        )
        added = await service._add(duplicate)
        await session.commit()
        total = await session.scalar(text("SELECT count(*) FROM suggestions"))

    assert added == 0 and total == 3
    _ = suggestion
