"""The local-AI adapters (Ollama), tested against canned Ollama responses: no model needed."""

import json
import math
from collections.abc import Callable

import httpx
import pytest
from httpx import AsyncClient
from pydantic import BaseModel
from sqlalchemy import text

from app.db.session import SessionLocal
from app.embeddings.errors import EmbeddingError
from app.embeddings.ollama import OllamaEmbeddingProvider
from app.embeddings.types import EMBEDDING_DIMENSIONS
from app.llm.errors import LLMError
from app.llm.ollama import OllamaProvider, simplify_schema
from app.llm.types import (
    AssistantToolTurn,
    TextTurn,
    ToolCall,
    ToolDefinition,
    ToolResult,
    ToolResultsTurn,
)
from app.tools import default_registry
from tests.test_tasks import tasks_url

Handler = Callable[[httpx.Request], httpx.Response]


def server(handler: Handler) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return httpx.MockTransport(record), seen


def reply(message: dict | None = None, **extra) -> httpx.Response:
    body = {"model": "m", "message": {"role": "assistant", "content": "ok"}, "done": True, **extra}
    if message is not None:
        body["message"] = {"role": "assistant", "content": "", **message}
    return httpx.Response(200, json=body)


def provider_for(handler: Handler, **kwargs) -> tuple[OllamaProvider, list[httpx.Request]]:
    transport, seen = server(handler)
    return OllamaProvider(
        base_url="http://ollama.test", model="llama3.2:3b", timeout=5, num_ctx=4096,
        transport=transport, **kwargs,
    ), seen


def payload_of(request: httpx.Request) -> dict:
    return json.loads(request.content)


async def ask(provider: OllamaProvider, text: str = "hi", tools=()):
    return await provider.generate(system="SYS", turns=[TextTurn("user", text)], tools=list(tools))


# --- Schema flattening ------------------------------------------------------------------------


class Priority(BaseModel):
    pass


def test_references_are_inlined_titles_dropped_and_optionals_collapsed() -> None:
    schema = {
        "$defs": {"Kind": {"enum": ["a", "b"], "title": "Kind", "type": "string"}},
        "title": "Args",
        "type": "object",
        "properties": {
            "kind": {"$ref": "#/$defs/Kind", "description": "Which kind"},
            "subject": {"anyOf": [{"type": "string", "maxLength": 5}, {"type": "null"}], "default": None, "title": "Subject"},
            "tags": {"type": "array", "items": {"$ref": "#/$defs/Kind"}},
        },
        "required": ["kind"],
    }

    simple = simplify_schema(schema)

    assert simple["properties"]["kind"] == {"enum": ["a", "b"], "type": "string", "description": "Which kind"}
    assert simple["properties"]["subject"] == {"type": "string", "maxLength": 5, "default": None}
    assert simple["properties"]["tags"]["items"] == {"enum": ["a", "b"], "type": "string"}
    assert simple["required"] == ["kind"]
    assert "$defs" not in simple and "title" not in simple


def test_an_argument_that_is_named_title_survives() -> None:
    schema = {
        "title": "CreateTaskInput",
        "type": "object",
        "properties": {"title": {"title": "Title", "type": "string"}, "description": {"type": "string"}},
        "required": ["title"],
    }

    simple = simplify_schema(schema)

    assert set(simple["properties"]) == {"title", "description"}
    assert simple["properties"]["title"] == {"type": "string"}


def test_anyof_with_several_real_options_is_left_alone() -> None:
    schema = {"type": "object", "properties": {"v": {"anyOf": [{"type": "string"}, {"type": "integer"}]}}}

    assert simplify_schema(schema)["properties"]["v"]["anyOf"] == [{"type": "string"}, {"type": "integer"}]


def test_recursive_references_do_not_loop_forever() -> None:
    schema = {"$defs": {"Node": {"type": "object", "properties": {"next": {"$ref": "#/$defs/Node"}}}},
              "$ref": "#/$defs/Node"}

    assert simplify_schema(schema)["type"] == "object"


def test_every_real_tool_flattens_to_a_clean_object_schema() -> None:
    definitions = default_registry().definitions()
    assert len(definitions) >= 10  # every tool the assistant has

    for definition in definitions:
        simple = simplify_schema(definition.input_schema)
        text = json.dumps(simple)
        assert simple["type"] == "object", definition.name
        assert "$ref" not in text and "$defs" not in text and '"anyOf": [{"type": "null"' not in text, definition.name
        # same arguments, same required list: only the noise is gone
        assert set(simple["properties"]) == set(definition.input_schema["properties"]), definition.name
        assert simple.get("required", []) == definition.input_schema.get("required", []), definition.name


# --- What we send ----------------------------------------------------------------------------------


async def test_a_chat_request_has_the_expected_shape() -> None:
    provider, seen = provider_for(lambda r: reply())
    tool = ToolDefinition("create_task", "Make a task.", {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]})

    await ask(provider, "Create a task", tools=[tool])

    request = seen[0]
    assert request.method == "POST" and str(request.url) == "http://ollama.test/api/chat"
    body = payload_of(request)
    assert body["model"] == "llama3.2:3b" and body["stream"] is False
    assert body["options"] == {"temperature": 0.2, "num_ctx": 4096}
    assert body["messages"] == [{"role": "system", "content": "SYS"}, {"role": "user", "content": "Create a task"}]
    assert body["tools"] == [{"type": "function", "function": {
        "name": "create_task", "description": "Make a task.",
        "parameters": {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]},
    }}]


async def test_no_tools_key_when_there_are_no_tools() -> None:
    provider, seen = provider_for(lambda r: reply())

    await ask(provider)

    assert "tools" not in payload_of(seen[0])


async def test_tool_calls_and_their_results_are_sent_back_in_ollamas_format() -> None:
    provider, seen = provider_for(lambda r: reply({"content": "Done."}))
    turns = [
        TextTurn("user", "Make two things"),
        AssistantToolTurn("Working on it", [ToolCall("c1", "create_task", {"title": "A"}), ToolCall("c2", "create_note", {"title": "B"})]),
        ToolResultsTurn([ToolResult("c1", '{"ok": true}'), ToolResult("c2", '{"ok": false, "error": "x"}', is_error=True)]),
    ]

    await provider.generate(system="SYS", turns=turns, tools=[])

    messages = payload_of(seen[0])["messages"]
    assert messages[2] == {"role": "assistant", "content": "Working on it", "tool_calls": [
        {"function": {"name": "create_task", "arguments": {"title": "A"}}},
        {"function": {"name": "create_note", "arguments": {"title": "B"}}},
    ]}
    assert messages[3] == {"role": "tool", "tool_name": "create_task", "content": '{"ok": true}'}
    assert messages[4] == {"role": "tool", "tool_name": "create_note", "content": '{"ok": false, "error": "x"}'}


# --- What we read -----------------------------------------------------------------------------------


async def test_a_plain_answer_is_parsed_with_token_counts() -> None:
    provider, _ = provider_for(lambda r: reply({"content": "Hello there"}, prompt_eval_count=120, eval_count=8))

    result = await ask(provider)

    assert (result.text, result.tool_calls, result.stop_reason) == ("Hello there", [], "end_turn")
    assert (result.input_tokens, result.output_tokens) == (120, 8)


async def test_tool_calls_are_parsed_and_given_unique_ids() -> None:
    provider, _ = provider_for(lambda r: reply({"tool_calls": [
        {"function": {"name": "create_task", "arguments": {"title": "A", "priority": "high"}}},
        {"function": {"name": "search_notes", "arguments": {"query": "x"}}},
    ]}))

    result = await ask(provider)

    assert result.stop_reason == "tool_use"
    assert [(c.name, c.input) for c in result.tool_calls] == [
        ("create_task", {"title": "A", "priority": "high"}), ("search_notes", {"query": "x"}),
    ]
    ids = [c.id for c in result.tool_calls]
    assert len(set(ids)) == 2 and all(i.startswith("ollama_") for i in ids)


@pytest.mark.parametrize("arguments,expected", [
    ('{"title": "From text"}', {"title": "From text"}),  # some versions send JSON text
    ("not json at all", {}),
    ('["a list"]', {}),
    (None, {}),
    (42, {}),
])
async def test_odd_tool_arguments_become_a_dict_never_a_crash(arguments, expected) -> None:
    provider, _ = provider_for(lambda r: reply({"tool_calls": [{"function": {"name": "t", "arguments": arguments}}]}))

    result = await ask(provider)

    assert result.tool_calls[0].input == expected


async def test_malformed_tool_calls_are_skipped() -> None:
    provider, _ = provider_for(lambda r: reply({"tool_calls": [
        {"function": {"arguments": {}}}, {"function": {"name": 7}}, "junk", {"nothing": 1},
        {"function": {"name": "real", "arguments": {}}},
    ]}))

    result = await ask(provider)

    assert [c.name for c in result.tool_calls] == ["real"]


async def test_a_cut_off_answer_is_reported_as_such() -> None:
    provider, _ = provider_for(lambda r: reply({"content": "Partial"}, done_reason="length"))

    assert (await ask(provider)).stop_reason == "max_tokens"


async def test_odd_token_counts_are_ignored() -> None:
    provider, _ = provider_for(lambda r: reply(prompt_eval_count=True, eval_count="many"))

    result = await ask(provider)

    assert result.input_tokens is None and result.output_tokens is None


async def test_non_text_content_becomes_empty_text() -> None:
    provider, _ = provider_for(lambda r: reply({"content": None}))

    assert (await ask(provider)).text == ""


@pytest.mark.parametrize("body", [{"done": True}, {"message": "just a string"}, {"message": None}])
async def test_a_reply_without_a_message_is_an_llm_error(body) -> None:
    provider, _ = provider_for(lambda r: httpx.Response(200, json=body))

    with pytest.raises(LLMError, match="no message"):
        await ask(provider)


# --- When Ollama isn't there ------------------------------------------------------------------------


async def test_ollama_not_running_says_how_to_start_it() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    provider, _ = provider_for(refuse)

    with pytest.raises(LLMError, match="Cannot reach Ollama at http://ollama.test.*running"):
        await ask(provider)


async def test_a_slow_model_says_how_to_cope() -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow")

    provider, _ = provider_for(slow)

    with pytest.raises(LLMError, match="OLLAMA_TIMEOUT_SECONDS"):
        await ask(provider)


async def test_a_missing_model_says_which_to_install() -> None:
    provider, _ = provider_for(lambda r: httpx.Response(404, json={"error": "model 'llama3.2:3b' not found"}))

    with pytest.raises(LLMError, match="ollama pull llama3.2:3b"):
        await ask(provider)


@pytest.mark.parametrize("response,match", [
    (httpx.Response(500, text="boom"), "HTTP 500"),
    (httpx.Response(200, text="<html>not json</html>"), "not JSON"),
    (httpx.Response(200, json=["a", "list"]), "unexpected"),
])
async def test_other_failures_become_llm_errors(response, match) -> None:
    provider, _ = provider_for(lambda r: response)

    with pytest.raises(LLMError, match=match):
        await ask(provider)


async def test_error_messages_never_contain_what_the_user_wrote() -> None:
    provider, _ = provider_for(lambda r: httpx.Response(500, text="boom"))

    with pytest.raises(LLMError) as caught:
        await provider.generate(system="SYS", turns=[TextTurn("user", "MY SECRET PLANS")], tools=[])

    assert "SECRET" not in str(caught.value)


# --- Inside the real app ----------------------------------------------------------------------------


def fake_ollama_that_creates_a_task(seen_messages: list):
    """Behaves like a tool-calling model: asks for create_task, then reports the result."""

    def handler(request: httpx.Request) -> httpx.Response:
        messages = payload_of(request)["messages"]
        seen_messages.append(messages)
        if messages[-1]["role"] == "tool":
            result = json.loads(messages[-1]["content"])
            return reply({"content": f"Created “{result['task']['title']}”."}, prompt_eval_count=50, eval_count=9)
        return reply({"tool_calls": [{"function": {"name": "create_task",
                      "arguments": {"title": "Call Ram", "priority": "high"}}}]}, prompt_eval_count=40, eval_count=6)

    return handler


async def chat(client: AsyncClient, user, message: str, expect: int = 200):
    response = await client.post(
        f"/api/v1/workspaces/{user.workspace_id}/assistant/chat",
        json={"message": message, "timezone": "UTC"}, headers=user.headers,
    )
    assert response.status_code == expect, response.text
    return response.json()


async def test_the_whole_assistant_runs_on_an_ollama_model(make_user, client, use_provider) -> None:
    alice = await make_user()
    seen: list = []
    provider, _ = provider_for(fake_ollama_that_creates_a_task(seen))
    use_provider(provider)

    body = await chat(client, alice, "Call Ram")

    message = body["message"]
    assert body["provider"] == "ollama" and message["provider"] == "ollama"
    assert message["content"] == "Created “Call Ram”."
    assert message["tool_events"][0]["name"] == "create_task" and message["tool_events"][0]["ok"]
    async with SessionLocal() as session:  # token use is stored, summed over both round trips
        row = (await session.execute(text("SELECT input_tokens, output_tokens FROM messages WHERE role = 'assistant'"))).one()
    assert (row.input_tokens, row.output_tokens) == (90, 15)
    tasks = (await client.get(tasks_url(alice.workspace_id), headers=alice.headers)).json()
    assert [(t["title"], t["priority"]) for t in tasks["items"]] == [("Call Ram", "high")]
    # the second request carried the tool's result back, labelled with the tool's name
    tool_message = seen[1][-1]
    assert tool_message["role"] == "tool" and tool_message["tool_name"] == "create_task"
    assert json.loads(tool_message["content"])["ok"] is True


async def test_a_misbehaving_local_model_cannot_do_forbidden_things(make_user, client, use_provider) -> None:
    alice = await make_user()

    def handler(request: httpx.Request) -> httpx.Response:
        if payload_of(request)["messages"][-1]["role"] == "tool":
            return reply({"content": "I tried."})
        return reply({"tool_calls": [
            {"function": {"name": "delete_everything", "arguments": {}}},
            {"function": {"name": "create_task", "arguments": {"title": "Sneaky", "workspace_id": "00000000-0000-0000-0000-000000000000"}}},
        ]})

    provider, _ = provider_for(handler)
    use_provider(provider)

    body = await chat(client, alice, "do bad things")

    events = body["message"]["tool_events"]
    assert [e["ok"] for e in events] == [False, False]  # unknown tool; unknown argument rejected
    tasks = (await client.get(tasks_url(alice.workspace_id), headers=alice.headers)).json()
    assert tasks["total"] == 0


async def test_the_status_names_the_local_model(make_user, client, use_provider) -> None:
    alice = await make_user()
    provider, _ = provider_for(lambda r: reply())
    use_provider(provider)

    response = await client.get(f"/api/v1/workspaces/{alice.workspace_id}/assistant/status", headers=alice.headers)

    assert response.json() == {"provider": "ollama", "demo": False, "model": "llama3.2:3b"}


async def test_the_demo_model_has_no_model_name(make_user, client) -> None:
    alice = await make_user()

    response = await client.get(f"/api/v1/workspaces/{alice.workspace_id}/assistant/status", headers=alice.headers)

    assert response.json() == {"provider": "fake", "demo": True, "model": None}


async def test_when_ollama_is_down_chat_answers_503_style_and_keeps_the_question(make_user, client, use_provider) -> None:
    alice = await make_user()

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    provider, _ = provider_for(refuse)
    use_provider(provider)

    body = await chat(client, alice, "Are you there?", expect=502)

    assert body["error"]["code"] == "ASSISTANT_UNAVAILABLE"
    assert "ollama" not in json.dumps(body).lower()  # the user sees a generic message, not internals
    conversations = (await client.get(f"/api/v1/workspaces/{alice.workspace_id}/conversations", headers=alice.headers)).json()
    assert conversations["total"] == 1  # the question was saved


def test_the_factory_builds_ollama_providers_from_settings(monkeypatch) -> None:
    from app.core.config import get_settings
    from app.embeddings.factory import get_embedding_provider
    from app.llm.factory import get_llm_provider

    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "embedding_provider", "OLLAMA")
    monkeypatch.setattr(settings, "ollama_model", "qwen2.5:3b")
    monkeypatch.setattr(settings, "ollama_embedding_model", "all-minilm")
    monkeypatch.setattr(settings, "ollama_base_url", "http://example:1234/")
    get_llm_provider.cache_clear()
    get_embedding_provider.cache_clear()
    try:
        chat_model, embedder = get_llm_provider(), get_embedding_provider()
        assert isinstance(chat_model, OllamaProvider) and chat_model.model == "qwen2.5:3b"
        assert chat_model.client.base_url == "http://example:1234"  # trailing slash tidied
        assert isinstance(embedder, OllamaEmbeddingProvider) and embedder.model == "all-minilm"
        monkeypatch.setattr(settings, "llm_provider", "nonsense")
        get_llm_provider.cache_clear()
        with pytest.raises(RuntimeError, match="fake, ollama"):
            get_llm_provider()
    finally:
        get_llm_provider.cache_clear()
        get_embedding_provider.cache_clear()


# --- Embeddings -------------------------------------------------------------------------------------


def vector(seed: float = 1.0, size: int = EMBEDDING_DIMENSIONS) -> list[float]:
    return [seed * (i % 7 + 1) for i in range(size)]


def embed_server(handler: Handler | None = None):
    def default(request: httpx.Request) -> httpx.Response:
        texts = payload_of(request)["input"]
        return httpx.Response(200, json={"model": "all-minilm", "embeddings": [vector(float(i + 1)) for i in range(len(texts))]})

    transport, seen = server(handler or default)
    return OllamaEmbeddingProvider(base_url="http://ollama.test", model="all-minilm", timeout=5, transport=transport), seen


async def test_embeddings_are_requested_and_returned_as_unit_vectors() -> None:
    provider, seen = embed_server()

    vectors = await provider.embed(["first", "second"])

    assert str(seen[0].url) == "http://ollama.test/api/embed"
    assert payload_of(seen[0]) == {"model": "all-minilm", "input": ["first", "second"]}
    assert len(vectors) == 2 and all(len(v) == EMBEDDING_DIMENSIONS for v in vectors)
    assert all(math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, rel_tol=1e-9) for v in vectors)


async def test_many_texts_are_sent_in_batches_and_keep_their_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        texts = payload_of(request)["input"]
        return httpx.Response(200, json={"embeddings": [[float(t.split("-")[1])] + [0.0] * (EMBEDDING_DIMENSIONS - 1) for t in texts]})

    provider, seen = embed_server(handler)

    vectors = await provider.embed([f"text-{i + 1}" for i in range(70)])

    assert [len(payload_of(r)["input"]) for r in seen] == [32, 32, 6]
    assert len(vectors) == 70 and all(v[0] == 1.0 for v in vectors)  # each normalised to a unit vector


async def test_no_texts_means_no_request() -> None:
    provider, seen = embed_server()

    assert await provider.embed([]) == [] and seen == []


async def test_a_model_with_the_wrong_vector_width_is_refused_clearly() -> None:
    provider, _ = embed_server(lambda r: httpx.Response(200, json={"embeddings": [vector(size=768)]}))

    with pytest.raises(EmbeddingError, match="768.*384.*all-minilm"):
        await provider.embed(["x"])


@pytest.mark.parametrize("body", [
    {"embeddings": []},
    {"embeddings": "nope"},
    {},
    {"embeddings": [["a", "b"]]},
    {"embeddings": [[True] * EMBEDDING_DIMENSIONS]},
    {"embeddings": ["not a vector"]},
])
async def test_malformed_embedding_replies_are_errors(body) -> None:
    provider, _ = embed_server(lambda r: httpx.Response(200, json=body))

    with pytest.raises(EmbeddingError):
        await provider.embed(["x"])


async def test_a_zero_vector_does_not_divide_by_zero() -> None:
    provider, _ = embed_server(lambda r: httpx.Response(200, json={"embeddings": [[0.0] * EMBEDDING_DIMENSIONS]}))

    assert await provider.embed(["x"]) == [[0.0] * EMBEDDING_DIMENSIONS]


async def test_embedding_failures_are_clean_app_errors() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    provider, _ = embed_server(refuse)

    with pytest.raises(EmbeddingError) as caught:
        await provider.embed(["private words"])

    assert caught.value.status_code == 502 and "Cannot reach Ollama" in caught.value.message
    assert "private" not in caught.value.message
    missing, _ = embed_server(lambda r: httpx.Response(404, json={"error": "not found"}))
    with pytest.raises(EmbeddingError, match="ollama pull all-minilm"):
        await missing.embed(["x"])


async def test_search_reports_a_helpful_502_when_embeddings_are_down(make_user, client, monkeypatch) -> None:
    from app.services import document_service

    alice = await make_user()

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    down, _ = embed_server(refuse)
    monkeypatch.setattr(document_service, "get_embedding_provider", lambda: down)

    response = await client.get(
        f"/api/v1/workspaces/{alice.workspace_id}/documents/search", params={"q": "anything"}, headers=alice.headers
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "EMBEDDINGS_UNAVAILABLE"
    assert "Cannot reach Ollama" in response.json()["error"]["message"]


async def test_a_document_fails_with_a_helpful_reason_when_embeddings_are_down(make_user, client, monkeypatch) -> None:
    from app.services import document_processing
    from tests.test_documents import upload

    alice = await make_user()

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    down, _ = embed_server(refuse)
    monkeypatch.setattr(document_processing, "get_embedding_provider", lambda: down)

    created = await upload(client, alice, "notes.txt", b"some text worth indexing")
    document = (await client.get(f"/api/v1/workspaces/{alice.workspace_id}/documents/{created['id']}", headers=alice.headers)).json()

    assert document["status"] == "failed"
    assert "Cannot reach Ollama" in document["error"]  # says what to fix
    assert "worth indexing" not in document["error"]  # and not what the document says
