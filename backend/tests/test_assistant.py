import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.llm.errors import LLMError
from app.llm.types import AssistantToolTurn, TextTurn, ToolResultsTurn
from tests.fakes import ScriptedProvider, call_tool, say

TZ = "Asia/Kathmandu"


def base(workspace_id: str) -> str:
    return f"/api/v1/workspaces/{workspace_id}"


async def chat(client: AsyncClient, user, message: str, **extra):
    return await client.post(
        f"{base(user.workspace_id)}/assistant/chat",
        json={"message": message, "timezone": TZ, **extra},
        headers=user.headers,
    )


async def tasks_of(client: AsyncClient, user) -> dict:
    return (await client.get(f"{base(user.workspace_id)}/tasks", headers=user.headers)).json()


def local_today() -> datetime:
    return datetime.now(ZoneInfo(TZ))


async def test_status_reports_demo_mode_and_messages_carry_their_provider(
    make_user, client, use_provider
) -> None:
    alice = await make_user()
    url = f"{base(alice.workspace_id)}/assistant/status"

    demo = (await client.get(url, headers=alice.headers)).json()
    reply = (await chat(client, alice, "hello")).json()
    use_provider(ScriptedProvider())
    real = (await client.get(url, headers=alice.headers)).json()

    assert demo == {"provider": "fake", "demo": True, "model": None}
    assert real == {"provider": "scripted", "demo": False, "model": None}
    assert reply["message"]["provider"] == "fake"


async def test_status_requires_membership(make_user, client) -> None:
    alice = await make_user("alice@example.com", "Alice")
    bob = await make_user("bob@example.com", "Bob")
    url = f"{base(alice.workspace_id)}/assistant/status"

    assert (await client.get(url)).status_code == 401
    assert (await client.get(url, headers=bob.headers)).status_code == 404


# --- The demo (fake) provider, end to end ---------------------------------------


async def test_fake_provider_creates_a_task_from_natural_language(make_user, client) -> None:
    alice = await make_user()

    response = await chat(client, alice, "Create a high priority task to finish my proposal tomorrow")

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "fake"
    event = body["message"]["tool_events"][0]
    assert (event["name"], event["ok"]) == ("create_task", True)
    assert "Finish my proposal" in body["message"]["content"]

    task = (await tasks_of(client, alice))["items"][0]
    assert task["title"] == "Finish my proposal"
    assert task["priority"] == "high"
    assert task["source"] == "assistant"
    due_local = datetime.fromisoformat(task["due_date"]).astimezone(ZoneInfo(TZ))
    assert due_local.date() == (local_today() + timedelta(days=1)).date()  # "tomorrow" in the user's zone
    assert (due_local.hour, due_local.minute) == (23, 59)  # end of that day


async def test_fake_provider_reminder_for_next_monday(make_user, client) -> None:
    alice = await make_user()

    await chat(client, alice, "Remind me to call Ram next Monday")

    task = (await tasks_of(client, alice))["items"][0]
    today = local_today().date()
    expected = today + timedelta(days=(0 - today.weekday()) % 7 or 7)
    assert task["title"] == "Call Ram"
    assert datetime.fromisoformat(task["due_date"]).astimezone(ZoneInfo(TZ)).date() == expected


async def test_fake_provider_searches_overdue_tasks(make_user, client) -> None:
    alice = await make_user()
    past = (datetime.now(ZoneInfo("UTC")) - timedelta(days=3)).isoformat()
    await client.post(f"{base(alice.workspace_id)}/tasks", json={"title": "Old thing", "due_date": past}, headers=alice.headers)
    await client.post(f"{base(alice.workspace_id)}/tasks", json={"title": "No deadline"}, headers=alice.headers)

    body = (await chat(client, alice, "What are my overdue tasks?")).json()

    event = body["message"]["tool_events"][0]
    assert event["name"] == "search_tasks"
    assert [t["title"] for t in event["result"]["tasks"]] == ["Old thing"]
    assert "Old thing" in body["message"]["content"]


async def test_fake_provider_creates_and_finds_notes(make_user, client) -> None:
    alice = await make_user()

    created = (await chat(client, alice, "Create a note called Rural markets saying expand distribution")).json()
    found = (await chat(client, alice, "Search notes for distribution")).json()

    assert created["message"]["tool_events"][0]["name"] == "create_note"
    notes = (await client.get(f"{base(alice.workspace_id)}/notes", headers=alice.headers)).json()["items"]
    assert [n["title"] for n in notes] == ["Rural markets"]
    assert found["message"]["tool_events"][0]["result"]["total"] == 1


async def test_fake_provider_explains_itself_when_it_does_not_understand(make_user, client) -> None:
    alice = await make_user()

    body = (await chat(client, alice, "What is the meaning of life?")).json()

    assert body["message"]["tool_events"] == []
    assert "demo mode" in body["message"]["content"]


# --- Tool safety (the model is untrusted) -------------------------------------------


async def test_unknown_tool_requested_by_the_model_is_reported_not_executed(
    make_user, client, use_provider
) -> None:
    alice = await make_user()
    provider = use_provider(ScriptedProvider(call_tool("delete_all_tasks", {}), say("Sorry, I can't do that.")))

    body = (await chat(client, alice, "wipe everything")).json()

    event = body["message"]["tool_events"][0]
    assert event["ok"] is False and "Unknown tool" in event["error"]
    assert body["message"]["content"] == "Sorry, I can't do that."
    # the failure was handed back to the model as an error result
    results = provider.calls[1]["turns"][-1]
    assert isinstance(results, ToolResultsTurn) and results.results[0].is_error


async def test_invalid_tool_arguments_create_nothing(make_user, client, use_provider) -> None:
    alice = await make_user()
    use_provider(
        ScriptedProvider(call_tool("create_task", {"title": "", "priority": "critical"}), say("That failed."))
    )

    body = (await chat(client, alice, "make a task")).json()

    event = body["message"]["tool_events"][0]
    assert event["ok"] is False
    assert "title" in event["error"] and "priority" in event["error"]
    assert (await tasks_of(client, alice))["total"] == 0


async def test_model_cannot_choose_the_workspace(make_user, client, use_provider) -> None:
    """Prompt injection could make the model try to write into someone else's workspace."""
    alice = await make_user("alice@example.com", "Alice")
    bob = await make_user("bob@example.com", "Bob")
    use_provider(
        ScriptedProvider(
            call_tool("create_task", {"title": "planted", "workspace_id": bob.workspace_id}),
            say("Tried."),
        )
    )

    body = (await chat(client, alice, "put a task in bob's workspace")).json()

    event = body["message"]["tool_events"][0]
    assert event["ok"] is False and "workspace_id" in event["error"]
    assert (await tasks_of(client, alice))["total"] == 0
    assert (await tasks_of(client, bob))["total"] == 0


async def test_tool_created_records_land_in_the_callers_workspace_only(make_user, client, use_provider) -> None:
    alice = await make_user("alice@example.com", "Alice")
    bob = await make_user("bob@example.com", "Bob")
    use_provider(ScriptedProvider(call_tool("create_task", {"title": "Mine"}), say("Done.")))

    await chat(client, alice, "add a task")

    assert [t["title"] for t in (await tasks_of(client, alice))["items"]] == ["Mine"]
    assert (await tasks_of(client, bob))["total"] == 0


async def test_assistant_search_never_sees_other_workspaces(make_user, client) -> None:
    alice = await make_user("alice@example.com", "Alice")
    bob = await make_user("bob@example.com", "Bob")
    await client.post(f"{base(alice.workspace_id)}/tasks", json={"title": "Alice secret"}, headers=alice.headers)
    await client.post(f"{base(alice.workspace_id)}/notes", json={"title": "Alice note", "content": "budget"}, headers=alice.headers)

    tasks = (await chat(client, bob, "Show my tasks")).json()
    notes = (await chat(client, bob, "Search notes for budget")).json()

    assert tasks["message"]["tool_events"][0]["result"]["total"] == 0
    assert notes["message"]["tool_events"][0]["result"]["total"] == 0
    assert "Alice" not in tasks["message"]["content"] + notes["message"]["content"]


async def test_loop_stops_at_the_iteration_limit(make_user, client, use_provider) -> None:
    alice = await make_user()
    provider = use_provider(ScriptedProvider(then=call_tool("search_tasks", {})))

    body = (await chat(client, alice, "loop forever")).json()

    assert len(provider.calls) == get_settings().assistant_max_iterations
    assert "step limit" in body["message"]["content"]


async def test_provider_failure_returns_502_and_keeps_the_users_message(
    make_user, client, use_provider
) -> None:
    alice = await make_user()
    use_provider(ScriptedProvider(LLMError("upstream exploded: key=sk-secret")))

    response = await chat(client, alice, "hello there")

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "ASSISTANT_UNAVAILABLE"
    assert "sk-secret" not in response.text
    listing = (await client.get(f"{base(alice.workspace_id)}/conversations", headers=alice.headers)).json()
    detail = (
        await client.get(f"{base(alice.workspace_id)}/conversations/{listing['items'][0]['id']}", headers=alice.headers)
    ).json()
    assert [(m["role"], m["content"]) for m in detail["messages"]] == [("user", "hello there")]


async def test_empty_model_reply_gets_a_fallback_message(make_user, client, use_provider) -> None:
    alice = await make_user()
    use_provider(ScriptedProvider(say("   ")))

    body = (await chat(client, alice, "hi")).json()

    assert body["message"]["content"].strip() != ""


# --- Conversations and context -----------------------------------------------------------


async def test_conversation_continues_and_sends_prior_turns(make_user, client, use_provider) -> None:
    alice = await make_user()
    provider = use_provider(ScriptedProvider(say("Hello!"), say("Fine.")))

    first = (await chat(client, alice, "first")).json()
    await chat(client, alice, "second", conversation_id=first["conversation_id"])

    assert provider.calls[1]["turns"] == [
        TextTurn("user", "first"),
        TextTurn("assistant", "Hello!"),
        TextTurn("user", "second"),
    ]
    assert provider.calls[1]["tools"], "the tool definitions are offered to the model"
    assert "Current date:" in provider.calls[1]["system"]


async def test_only_recent_history_is_sent_and_it_starts_with_a_user_turn(
    make_user, client, use_provider, monkeypatch
) -> None:
    alice = await make_user()
    monkeypatch.setattr(get_settings(), "assistant_history_messages", 3)
    provider = use_provider(ScriptedProvider(say("a1"), say("a2"), say("a3"), say("a4")))

    conversation_id = (await chat(client, alice, "u1")).json()["conversation_id"]
    for text in ("u2", "u3", "u4"):
        await chat(client, alice, text, conversation_id=conversation_id)

    # history window = last 3 stored messages [a2, u3, a3]; the leading assistant turn is dropped
    assert provider.calls[3]["turns"] == [
        TextTurn("user", "u3"),
        TextTurn("assistant", "a3"),
        TextTurn("user", "u4"),
    ]


async def test_retry_after_a_failure_merges_consecutive_user_turns(make_user, client, use_provider) -> None:
    alice = await make_user()
    provider = use_provider(ScriptedProvider(LLMError("down"), say("Back.")))
    await chat(client, alice, "first try")
    conversation_id = (
        await client.get(f"{base(alice.workspace_id)}/conversations", headers=alice.headers)
    ).json()["items"][0]["id"]

    await chat(client, alice, "second try", conversation_id=conversation_id)

    assert provider.calls[1]["turns"] == [TextTurn("user", "first try\n\nsecond try")]


async def test_conversation_detail_includes_tool_events(make_user, client) -> None:
    alice = await make_user()
    sent = (await chat(client, alice, "Create a task to water the plants")).json()

    detail = (
        await client.get(f"{base(alice.workspace_id)}/conversations/{sent['conversation_id']}", headers=alice.headers)
    ).json()

    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["tool_events"][0]["name"] == "create_task"
    assert detail["title"] == "Create a task to water the plants"


async def test_list_and_delete_conversations(make_user, client) -> None:
    alice = await make_user()
    first = (await chat(client, alice, "one")).json()["conversation_id"]
    await chat(client, alice, "two")
    url = f"{base(alice.workspace_id)}/conversations"

    listing = (await client.get(url, headers=alice.headers)).json()
    deleted = await client.delete(f"{url}/{first}", headers=alice.headers)
    after = await client.get(f"{url}/{first}", headers=alice.headers)

    assert listing["total"] == 2
    assert deleted.status_code == 204
    assert after.status_code == 404 and after.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"
    assert (await client.get(url, headers=alice.headers)).json()["total"] == 1


# --- Validation, authentication, isolation --------------------------------------------------


async def test_chat_validation(make_user, client) -> None:
    alice = await make_user()
    url = f"{base(alice.workspace_id)}/assistant/chat"

    for payload in (
        {},
        {"message": ""},
        {"message": "   "},
        {"message": "x" * 4001},
        {"message": "hi", "timezone": "Mars/Olympus"},
        {"message": "hi", "conversation_id": "not-a-uuid"},
    ):
        response = await client.post(url, json=payload, headers=alice.headers)
        assert response.status_code == 422, payload


@pytest.mark.parametrize(
    "browser_timezone",
    # Names Chromium/Edge actually report for these regions (legacy IANA aliases)
    ["Asia/Katmandu", "Asia/Calcutta", "Europe/Kiev", "Asia/Saigon", "America/Buenos_Aires", "Asia/Kathmandu", "UTC"],
)
async def test_timezone_names_reported_by_real_browsers_are_accepted(
    make_user, client, browser_timezone
) -> None:
    alice = await make_user()

    response = await client.post(
        f"{base(alice.workspace_id)}/assistant/chat",
        json={"message": "hello", "timezone": browser_timezone},
        headers=alice.headers,
    )

    assert response.status_code == 200, response.text


async def test_unknown_conversation_id_is_404(make_user, client) -> None:
    alice = await make_user()

    response = await chat(client, alice, "hi", conversation_id=str(uuid.uuid4()))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


async def test_assistant_requires_authentication(make_user, client) -> None:
    alice = await make_user()

    assert (await client.post(f"{base(alice.workspace_id)}/assistant/chat", json={"message": "hi"})).status_code == 401
    assert (await client.get(f"{base(alice.workspace_id)}/conversations")).status_code == 401


async def test_non_members_cannot_use_another_workspaces_assistant(make_user, client) -> None:
    alice = await make_user("alice@example.com", "Alice")
    bob = await make_user("bob@example.com", "Bob")
    conversation_id = (await chat(client, alice, "private")).json()["conversation_id"]
    alice_url = base(alice.workspace_id)

    attempts = [
        await client.post(f"{alice_url}/assistant/chat", json={"message": "hi"}, headers=bob.headers),
        await client.get(f"{alice_url}/conversations", headers=bob.headers),
        await client.get(f"{alice_url}/conversations/{conversation_id}", headers=bob.headers),
        await client.delete(f"{alice_url}/conversations/{conversation_id}", headers=bob.headers),
    ]

    for response in attempts:
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"


async def test_conversation_id_from_another_workspace_is_not_reachable(make_user, client) -> None:
    alice = await make_user("alice@example.com", "Alice")
    bob = await make_user("bob@example.com", "Bob")
    conversation_id = (await chat(client, alice, "private")).json()["conversation_id"]
    bob_url = base(bob.workspace_id)

    get = await client.get(f"{bob_url}/conversations/{conversation_id}", headers=bob.headers)
    cont = await chat(client, bob, "hi", conversation_id=conversation_id)
    delete = await client.delete(f"{bob_url}/conversations/{conversation_id}", headers=bob.headers)

    for response in (get, cont, delete):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"
    assert (await client.get(f"{base(alice.workspace_id)}/conversations/{conversation_id}", headers=alice.headers)).status_code == 200


async def test_each_user_lists_only_their_own_conversations(make_user, client) -> None:
    alice = await make_user("alice@example.com", "Alice")
    bob = await make_user("bob@example.com", "Bob")
    await chat(client, alice, "alice question")
    await chat(client, bob, "bob question")

    alice_list = (await client.get(f"{base(alice.workspace_id)}/conversations", headers=alice.headers)).json()
    bob_list = (await client.get(f"{base(bob.workspace_id)}/conversations", headers=bob.headers)).json()

    assert [c["title"] for c in alice_list["items"]] == ["alice question"]
    assert [c["title"] for c in bob_list["items"]] == ["bob question"]
