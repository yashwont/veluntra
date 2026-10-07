import json
import uuid
from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.memory import MemoryKind
from app.models.task import TaskPriority, TaskStatus
from app.services.search_service import SearchType, parse_query
from app.tools import default_registry
from app.tools.base import ToolContext
from tests.test_documents import upload
from tests.test_memories import add as add_memory
from tests.test_notes import create_note
from tests.test_tasks import create_task, iso


def search_url(workspace_id: str) -> str:
    return f"/api/v1/workspaces/{workspace_id}/search"


async def find(client: AsyncClient, user, q: str, expect: int = 200, **params) -> dict:
    response = await client.get(
        search_url(user.workspace_id), params={"q": q, **params}, headers=user.headers
    )
    assert response.status_code == expect, response.text
    return response.json()


def kinds(body: dict) -> list[str]:
    return [r["type"] for r in body["results"]]


def titles(body: dict) -> list[str]:
    return [r["title"] for r in body["results"]]


# --- Query parsing ------------------------------------------------------------------


def test_parse_plain_text() -> None:
    parsed = parse_query("  budget   review ")

    assert parsed.text == "budget review"
    assert not parsed.has_filters
    assert parsed.candidate_types() == set(SearchType)


def test_parse_extracts_filters_and_keeps_the_rest_as_text() -> None:
    parsed = parse_query("proposal priority:HIGH is:overdue status:in-progress tag:Work")

    assert parsed.text == "proposal"
    assert parsed.priority == TaskPriority.HIGH
    assert parsed.overdue is True
    assert parsed.status == TaskStatus.IN_PROGRESS
    assert parsed.tags == ["work"]


def test_parse_leaves_unrecognised_operators_in_the_text() -> None:
    parsed = parse_query("priority:urgentish foo:bar kind:nonsense is:fun type:widgets")

    assert parsed.text == "priority:urgentish foo:bar kind:nonsense is:fun type:widgets"
    assert not parsed.has_filters


def test_filters_narrow_the_content_types_they_apply_to() -> None:
    assert parse_query("tag:work").candidate_types() == {SearchType.NOTE}
    assert parse_query("is:overdue").candidate_types() == {SearchType.TASK}
    assert parse_query("kind:person").candidate_types() == {SearchType.MEMORY}
    assert parse_query("tag:work is:overdue").candidate_types() == set()  # nothing is both
    assert parse_query("x type:doc type:memories").types == {SearchType.DOCUMENT, SearchType.MEMORY}
    assert parse_query("x").candidate_types({SearchType.NOTE}) == {SearchType.NOTE}


# --- Searching across everything --------------------------------------------------


async def seed_budget(client, user) -> None:
    await create_task(client, user, title="Prepare the budget presentation")
    await create_note_budget(client, user)
    await upload(client, user, "budget.txt", b"The quarterly budget covers marketing spend and travel.")
    await add_memory(client, user, "Priya owns the budget approval process", kind="person", subject="Priya")


async def create_note_budget(client, user) -> None:
    await create_note(client, user, title="Budget notes", content="Numbers for the annual budget")


async def test_one_query_finds_every_kind_of_content(make_user, client) -> None:
    alice = await make_user()
    await seed_budget(client, alice)

    body = await find(client, alice, "budget")

    assert set(kinds(body)) == {"task", "note", "document", "memory"}
    assert body["applied"]["text"] == "budget"
    for result in body["results"]:
        assert result["score"] is not None and 0 <= result["score"] <= 1
        assert result["id"] and result["snippet"] is not None


async def test_results_are_ordered_by_relevance(make_user, client) -> None:
    alice = await make_user()
    await seed_budget(client, alice)

    scores = [r["score"] for r in (await find(client, alice, "budget"))["results"]]

    assert scores == sorted(scores, reverse=True)


async def test_a_title_match_outranks_a_body_match(make_user, client) -> None:
    alice = await make_user()
    await create_note(client, alice, title="Weekly planning", content="mention of the roadmap inside")
    await create_note(client, alice, title="Roadmap", content="plans")

    body = await find(client, alice, "roadmap", types=["note"])

    assert titles(body) == ["Roadmap", "Weekly planning"]


async def test_full_text_search_stems_words(make_user, client) -> None:
    alice = await make_user()
    await create_task(client, alice, title="Finishing the quarterly report")

    assert titles(await find(client, alice, "finish report")) == ["Finishing the quarterly report"]


async def test_documents_appear_once_with_their_best_passage(make_user, client) -> None:
    alice = await make_user()
    filler = "Garden notes: tomatoes need sun, basil likes water, and the weather turns cold in autumn. " * 10
    warranty_a = "Espresso machine warranty period: the warranty covers the machine for two years. " * 11
    warranty_b = "Warranty claims for the espresso machine must be filed within the warranty period. " * 11
    long_text = "\n\n".join([filler, warranty_a, filler, warranty_b, filler])
    await upload(client, alice, "manual.txt", long_text.encode())

    body = await find(client, alice, "espresso machine warranty period")

    docs = [r for r in body["results"] if r["type"] == "document"]
    assert len(docs) == 1
    assert docs[0]["title"] == "manual.txt"
    assert "arranty" in docs[0]["snippet"]


async def test_unrelated_queries_find_nothing(make_user, client) -> None:
    alice = await make_user()
    await seed_budget(client, alice)

    assert (await find(client, alice, "zebra giraffe"))["results"] == []


async def test_limit_and_types_parameters(make_user, client) -> None:
    alice = await make_user()
    await seed_budget(client, alice)
    await create_task(client, alice, title="Budget review meeting")

    limited = await find(client, alice, "budget", limit=2)
    only_tasks = await find(client, alice, "budget", types=["task"])
    notes_and_memories = await find(client, alice, "budget", types=["note", "memory"])

    assert len(limited["results"]) == 2
    assert set(kinds(only_tasks)) == {"task"} and len(only_tasks["results"]) == 2
    assert set(kinds(notes_and_memories)) == {"note", "memory"}
    assert (await find(client, alice, "budget", expect=422, limit=0))["error"]["code"] == "VALIDATION_ERROR"
    assert (await find(client, alice, "budget", expect=422, types=["emails"]))["error"]["code"] == "VALIDATION_ERROR"


# --- Structured filters -------------------------------------------------------------


async def test_priority_filter_with_text_searches_only_matching_tasks(make_user, client) -> None:
    alice = await make_user()
    await create_task(client, alice, title="Budget deck", priority="high")
    await create_task(client, alice, title="Budget email", priority="low")
    await create_note(client, alice, title="Budget notes")

    body = await find(client, alice, "budget priority:high")

    assert titles(body) == ["Budget deck"]
    assert body["applied"]["priority"] == "high"
    assert body["applied"]["types"] == ["task"]
    assert body["applied"]["text"] == "budget"


async def test_filter_only_queries_list_matches_newest_first_without_scores(make_user, client) -> None:
    alice = await make_user()
    await create_task(client, alice, title="Old overdue", due_date=iso(-timedelta(days=9)))
    await create_task(client, alice, title="Fresh overdue", due_date=iso(-timedelta(days=1)))
    await create_task(client, alice, title="Future", due_date=iso(timedelta(days=5)))
    await create_task(client, alice, title="Undated")

    body = await find(client, alice, "is:overdue")

    assert titles(body) == ["Fresh overdue", "Old overdue"]
    assert all(r["score"] is None for r in body["results"])
    assert body["applied"]["overdue"] is True


async def test_status_filter(make_user, client) -> None:
    alice = await make_user()
    await create_task(client, alice, title="Done thing", status="completed")
    await create_task(client, alice, title="Open thing")

    assert titles(await find(client, alice, "status:completed")) == ["Done thing"]
    assert titles(await find(client, alice, "thing status:todo")) == ["Open thing"]


async def test_tag_filter_searches_notes_only(make_user, client) -> None:
    alice = await make_user()
    await create_note(client, alice, title="Work plan", tags=["work"])
    await create_note(client, alice, title="Home plan", tags=["home"])
    await create_task(client, alice, title="Plan the sprint")

    body = await find(client, alice, "plan tag:work")

    assert titles(body) == ["Work plan"]
    assert body["results"][0]["tags"] == ["work"]


async def test_kind_filter_searches_memories_only(make_user, client) -> None:
    alice = await make_user()
    await add_memory(client, alice, "Ram runs the supplier firm", kind="person", subject="Ram")
    await add_memory(client, alice, "Supplier contract renews in May", kind="event")
    await create_task(client, alice, title="Call the supplier")

    with_text = await find(client, alice, "supplier kind:person")
    only_filter = await find(client, alice, "kind:event")

    assert titles(with_text) == ["Ram"]
    assert set(kinds(with_text)) == {"memory"}
    assert [r["kind"] for r in only_filter["results"]] == ["event"]


async def test_type_operator_alone_lists_that_kind(make_user, client) -> None:
    alice = await make_user()
    await create_note(client, alice, title="First")
    await create_note(client, alice, title="Second")
    await create_task(client, alice, title="A task")

    body = await find(client, alice, "type:notes")

    assert titles(body) == ["Second", "First"]
    assert body["applied"]["types"] == ["note"]


async def test_contradictory_filters_find_nothing(make_user, client) -> None:
    alice = await make_user()
    await create_note(client, alice, title="Work plan", tags=["work"])
    await create_task(client, alice, title="Plan", priority="high")

    body = await find(client, alice, "plan tag:work priority:high")

    assert body["results"] == []
    assert body["applied"]["types"] == []


async def test_empty_search_is_rejected_with_guidance(make_user, client) -> None:
    alice = await make_user()

    blank = await find(client, alice, "   ", expect=422)

    assert blank["error"]["code"] == "EMPTY_SEARCH"
    assert (await find(client, alice, "", expect=422))["error"]["code"] == "VALIDATION_ERROR"


# --- Access control -----------------------------------------------------------------


async def test_requires_authentication(make_user, client) -> None:
    alice = await make_user()

    response = await client.get(search_url(alice.workspace_id), params={"q": "x"})

    assert response.status_code == 401


async def test_search_never_crosses_workspaces(make_user, client) -> None:
    alice = await make_user("alice@example.com", "Alice")
    bob = await make_user("bob@example.com", "Bob")
    await seed_budget(client, alice)
    await create_task(client, alice, title="Budget overdue", due_date=iso(-timedelta(days=2)))

    assert (await find(client, bob, "budget"))["results"] == []
    assert (await find(client, bob, "is:overdue"))["results"] == []
    assert (await find(client, bob, "type:notes"))["results"] == []
    forbidden = await client.get(
        search_url(alice.workspace_id), params={"q": "budget"}, headers=bob.headers
    )
    assert forbidden.status_code == 404


# --- Assistant tool ---------------------------------------------------------------------


async def test_assistant_tool_searches_everything_in_the_current_workspace(make_user, client) -> None:
    alice = await make_user("alice@example.com", "Alice")
    bob = await make_user("bob@example.com", "Bob")
    await seed_budget(client, alice)

    async def run(user, args: dict) -> dict:
        async with SessionLocal() as session:
            ctx = ToolContext(
                session=session,
                workspace_id=uuid.UUID(user.workspace_id),
                user_id=uuid.UUID(user.user_id),
                timezone=ZoneInfo("UTC"),
            )
            return json.loads((await default_registry().execute("search_everything", args, ctx)).content)

    mine = await run(alice, {"query": "budget"})
    theirs = await run(bob, {"query": "budget"})
    invalid = await run(alice, {"query": "x", "types": ["emails"]})
    empty = await run(alice, {"query": "   "})

    assert mine["ok"] and {r["type"] for r in mine["results"]} == {"task", "note", "document", "memory"}
    assert theirs == {"ok": True, "results": []}
    assert invalid["ok"] is False
    assert empty["ok"] is False and "Enter some words" in empty["error"]


async def test_the_assistant_can_search_everywhere(make_user, client) -> None:
    alice = await make_user()
    await seed_budget(client, alice)

    response = await client.post(
        f"/api/v1/workspaces/{alice.workspace_id}/assistant/chat",
        json={"message": "Search everything for budget", "timezone": "UTC"},
        headers=alice.headers,
    )

    assert response.status_code == 200
    message = response.json()["message"]
    assert message["tool_events"][0]["name"] == "search_everything"
    assert "[task]" in message["content"] and "[memory]" in message["content"]


@pytest.mark.parametrize("kind", [k.value for k in MemoryKind])
def test_every_memory_kind_is_a_valid_filter(kind: str) -> None:
    assert parse_query(f"kind:{kind}").kind == MemoryKind(kind)
