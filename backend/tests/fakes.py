"""Test doubles for the LLM provider."""

import uuid
from collections.abc import Sequence
from typing import Any

from app.llm.types import LLMResponse, LLMTurn, ToolCall, ToolDefinition


def say(text: str) -> LLMResponse:
    return LLMResponse(text=text)


def call_tool(name: str, arguments: dict[str, Any], text: str = "") -> LLMResponse:
    return LLMResponse(
        text=text,
        tool_calls=[ToolCall(id=f"call_{uuid.uuid4().hex[:8]}", name=name, input=arguments)],
        stop_reason="tool_use",
    )


class ScriptedProvider:
    """Plays back prepared responses (or raises prepared exceptions) in order, and
    records what the app sent so tests can assert on it."""

    name = "scripted"

    def __init__(self, *script: LLMResponse | Exception, then: LLMResponse | None = None) -> None:
        self._script = list(script)
        self._then = then  # returned forever once the script runs out
        self.calls: list[dict[str, Any]] = []

    async def generate(
        self,
        *,
        system: str,
        turns: Sequence[LLMTurn],
        tools: Sequence[ToolDefinition],
    ) -> LLMResponse:
        self.calls.append({"system": system, "turns": list(turns), "tools": list(tools)})
        if self._script:
            item = self._script.pop(0)
        elif self._then is not None:
            item = self._then
        else:
            raise AssertionError("ScriptedProvider ran out of responses")
        if isinstance(item, Exception):
            raise item
        return item
