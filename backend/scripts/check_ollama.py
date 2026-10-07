"""Check that your local Ollama setup works for Veluntra, and say what to fix if not.

    docker compose exec backend python -m scripts.check_ollama

It exercises the same code the app uses: reaching Ollama, having the models, a plain
chat, a tool call (the part small models most often get wrong) and an embedding of the
right size. Nothing is saved. Takes a minute on a slow computer: the first request loads
the model into memory.
"""

import asyncio
import sys
import time
from dataclasses import dataclass

from app.core.config import get_settings
from app.embeddings.errors import EmbeddingError
from app.embeddings.ollama import OllamaEmbeddingProvider
from app.embeddings.types import EMBEDDING_DIMENSIONS
from app.integrations.ollama import OllamaClient, OllamaError
from app.llm.errors import LLMError
from app.llm.ollama import OllamaProvider
from app.llm.types import TextTurn, ToolDefinition


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def is_installed(wanted: str, installed: list[str]) -> bool:
    """`llama3.2` matches `llama3.2:latest`; `llama3.2:3b` must match exactly."""
    if ":" in wanted:
        return wanted in installed
    return any(name == wanted or name.split(":")[0] == wanted for name in installed)


ADD_TOOL = ToolDefinition(
    name="add_numbers",
    description="Add two numbers and return the sum.",
    input_schema={
        "type": "object",
        "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
        "required": ["a", "b"],
    },
)


async def diagnose(
    client: OllamaClient, chat: OllamaProvider, embeddings: OllamaEmbeddingProvider
) -> list[Check]:
    checks: list[Check] = []

    try:
        tags = await client.get("/api/tags")
    except OllamaError as exc:
        return [Check("Ollama is reachable", False, str(exc))]
    installed = [m.get("name", "") for m in tags.get("models", []) if isinstance(m, dict)]
    checks.append(Check("Ollama is reachable", True, f"{len(installed)} model(s) installed"))

    for label, model in (("chat model", chat.model), ("embedding model", embeddings.model)):
        found = is_installed(model, installed)
        checks.append(
            Check(
                f"{label} '{model}' is installed",
                found,
                "ready" if found else f"install it with:  ollama pull {model}",
            )
        )
    if not all(c.ok for c in checks):
        return checks

    started = time.monotonic()
    try:
        reply = await chat.generate(
            system="You are a terse assistant.",
            turns=[TextTurn("user", "Reply with the single word: ready")],
            tools=[],
        )
        took = time.monotonic() - started
        checks.append(Check("chat works", bool(reply.text.strip()), f"answered in {took:.0f}s"))
    except LLMError as exc:
        checks.append(Check("chat works", False, str(exc)))
        return checks

    try:
        reply = await chat.generate(
            system="You are a helpful assistant. Use tools when they help.",
            turns=[TextTurn("user", "What is 17 plus 25? Use the add_numbers tool.")],
            tools=[ADD_TOOL],
        )
        called = next((c for c in reply.tool_calls if c.name == "add_numbers"), None)
        checks.append(
            Check(
                "tool calling works",
                called is not None,
                f"the model called add_numbers with {called.input}"
                if called
                else "the model answered in words instead of calling the tool: it may not support "
                "tools. Try llama3.2:3b, llama3.1:8b or qwen2.5:3b.",
            )
        )
    except LLMError as exc:
        checks.append(Check("tool calling works", False, str(exc)))

    try:
        [vector] = await embeddings.embed(["hello world"])
        checks.append(Check("embeddings work", True, f"{len(vector)}-number vectors (expected {EMBEDDING_DIMENSIONS})"))
    except EmbeddingError as exc:
        checks.append(Check("embeddings work", False, str(exc)))
    return checks


async def main() -> int:
    settings = get_settings()
    chat = OllamaProvider()
    embeddings = OllamaEmbeddingProvider()
    print(f"Ollama at {settings.ollama_base_url}")
    print(f"  chat model:      {chat.model}")
    print(f"  embedding model: {embeddings.model}\n")

    checks = await diagnose(chat.client, chat, embeddings)
    for check in checks:
        print(f"  [{'ok' if check.ok else 'FAIL'}] {check.name}: {check.detail}")

    failed = [c for c in checks if not c.ok]
    print()
    if failed:
        print(f"{len(failed)} problem(s). Fix the first one above and run this again.")
        return 1
    print("All good. Set LLM_PROVIDER=ollama (and EMBEDDING_PROVIDER=ollama) in .env, then restart the API.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
