"""The check and reindex helper scripts."""

import json

import httpx
import pytest
from sqlalchemy import text

from app.db.session import SessionLocal
from app.embeddings.ollama import OllamaEmbeddingProvider
from app.embeddings.types import EMBEDDING_DIMENSIONS
from app.integrations.ollama import OllamaClient
from app.llm.ollama import OllamaProvider
from scripts.check_ollama import diagnose, is_installed
from scripts.reindex_embeddings import reindex
from tests.test_documents import upload
from tests.test_memories import add as add_memory

BASE = "http://ollama.test"


def stack(handler):
    """A chat provider and embedder talking to the same canned server."""
    transport = httpx.MockTransport(handler)
    chat = OllamaProvider(base_url=BASE, model="llama3.2:3b", timeout=5, num_ctx=4096, transport=transport)
    embed = OllamaEmbeddingProvider(base_url=BASE, model="all-minilm", timeout=5, transport=transport)
    return OllamaClient(BASE, 5, transport), chat, embed


def healthy(models=("llama3.2:3b", "all-minilm:latest"), calls_tool=True, dims=EMBEDDING_DIMENSIONS):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": n} for n in models]})
        if path == "/api/embed":
            return httpx.Response(200, json={"embeddings": [[0.5] * dims]})
        body = json.loads(request.content)
        if body.get("tools") and calls_tool:
            return httpx.Response(200, json={"message": {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "add_numbers", "arguments": {"a": 17, "b": 25}}}]}})
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "ready"}})

    return handler


def by_name(checks):
    return {c.name: c for c in checks}


@pytest.mark.parametrize("wanted,installed,expected", [
    ("llama3.2:3b", ["llama3.2:3b"], True),
    ("llama3.2:3b", ["llama3.2:1b", "llama3.2:latest"], False),  # a tag must match exactly
    ("llama3.2", ["llama3.2:latest"], True),  # no tag: any tag will do
    ("all-minilm", ["all-minilm:latest", "other:1b"], True),
    ("all-minilm", ["all-minilm-large:latest"], False),
    ("anything", [], False),
])
def test_installed_model_matching(wanted, installed, expected) -> None:
    assert is_installed(wanted, installed) is expected


async def test_a_healthy_setup_passes_every_check() -> None:
    checks = await diagnose(*stack(healthy()))

    assert [c.ok for c in checks] == [True] * 6
    names = [c.name for c in checks]
    assert names == [
        "Ollama is reachable", "chat model 'llama3.2:3b' is installed",
        "embedding model 'all-minilm' is installed", "chat works", "tool calling works", "embeddings work",
    ]
    assert "add_numbers" in by_name(checks)["tool calling works"].detail
    assert "384-number" in by_name(checks)["embeddings work"].detail


async def test_ollama_not_running_is_the_only_finding() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    checks = await diagnose(*stack(refuse))

    assert len(checks) == 1 and not checks[0].ok
    assert "Cannot reach Ollama" in checks[0].detail


async def test_missing_models_are_named_with_the_command_to_install_them() -> None:
    checks = by_name(await diagnose(*stack(healthy(models=["something-else:1b"]))))

    assert not checks["chat model 'llama3.2:3b' is installed"].ok
    assert "ollama pull llama3.2:3b" in checks["chat model 'llama3.2:3b' is installed"].detail
    assert "ollama pull all-minilm" in checks["embedding model 'all-minilm' is installed"].detail
    assert "chat works" not in checks  # it doesn't try to use what isn't there


async def test_a_model_that_cannot_call_tools_is_called_out_with_advice() -> None:
    checks = by_name(await diagnose(*stack(healthy(calls_tool=False))))

    assert checks["chat works"].ok
    assert not checks["tool calling works"].ok
    assert "may not support tools" in checks["tool calling works"].detail
    assert "llama3.2:3b" in checks["tool calling works"].detail


async def test_an_embedding_model_of_the_wrong_size_is_reported() -> None:
    checks = by_name(await diagnose(*stack(healthy(dims=768))))

    assert not checks["embeddings work"].ok
    assert "768" in checks["embeddings work"].detail and "all-minilm" in checks["embeddings work"].detail


# --- Reindexing ----------------------------------------------------------------------------------


class ConstantEmbedder:
    """Puts every text at the same recognisable point, so a re-embed is easy to spot."""

    name = "constant"

    async def embed(self, texts):
        return [[1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1) for _ in texts]


async def stored(table: str) -> list[str]:
    async with SessionLocal() as session:
        rows = await session.execute(text(f"SELECT embedding::text FROM {table} ORDER BY id"))
        return [r[0] for r in rows]


async def test_reindexing_recomputes_memory_and_document_vectors(make_user, client) -> None:
    alice = await make_user()
    await add_memory(client, alice, "Ram prefers email over calls", subject="Ram")
    await add_memory(client, alice, "Mobile app launches in November")
    created = await upload(client, alice, "notes.txt", b"Quarterly revenue grew twelve percent.")
    memories_before, chunks_before = await stored("memories"), await stored("document_chunks")

    counts = await reindex(ConstantEmbedder())

    assert counts == (2, 1)
    memories_after, chunks_after = await stored("memories"), await stored("document_chunks")
    assert memories_after != memories_before and chunks_after != chunks_before
    assert all(v.startswith("[1,0,0,") for v in memories_after + chunks_after)  # all re-embedded
    document = (await client.get(f"/api/v1/workspaces/{alice.workspace_id}/documents/{created['id']}", headers=alice.headers)).json()
    assert document["status"] == "ready" and document["chunk_count"] == 1  # no duplicate chunks left behind


async def test_reindexing_an_empty_database_is_fine() -> None:
    assert await reindex(ConstantEmbedder()) == (0, 0)


async def test_reindexing_repairs_documents_that_failed_before(make_user, client, monkeypatch) -> None:
    from app.services import document_processing

    alice = await make_user()

    class Down:
        name = "down"

        async def embed(self, texts):
            from app.embeddings.errors import EmbeddingError

            raise EmbeddingError("Cannot reach Ollama")

    monkeypatch.setattr(document_processing, "get_embedding_provider", lambda: Down())
    created = await upload(client, alice, "notes.txt", b"some words to index")
    url = f"/api/v1/workspaces/{alice.workspace_id}/documents/{created['id']}"
    assert (await client.get(url, headers=alice.headers)).json()["status"] == "failed"

    counts = await reindex(ConstantEmbedder())

    assert counts == (0, 1)
    assert (await client.get(url, headers=alice.headers)).json()["status"] == "ready"
