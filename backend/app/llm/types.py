"""Provider-neutral types for talking to an LLM.

These mirror how tool calling works in every major API: the model answers with
text and/or tool calls; we run the tools and send *all* the results back
together; repeat until the model answers without calling a tool. A provider
adapter (Anthropic, ...) translates these types to and from its own wire format.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]  # JSON Schema for the tool's arguments


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]  # untrusted: validated before anything runs


@dataclass(frozen=True)
class ToolResult:
    tool_call_id: str
    content: str  # JSON text shown to the model
    is_error: bool = False


@dataclass(frozen=True)
class TextTurn:
    role: Literal["user", "assistant"]
    text: str


@dataclass(frozen=True)
class AssistantToolTurn:
    """The model asked to run tools (and may have said something first)."""

    text: str
    tool_calls: list[ToolCall]


@dataclass(frozen=True)
class ToolResultsTurn:
    """Results for every tool call of the preceding AssistantToolTurn."""

    results: list[ToolResult]


LLMTurn = TextTurn | AssistantToolTurn | ToolResultsTurn

StopReason = Literal["end_turn", "tool_use", "max_tokens", "refusal"]


@dataclass(frozen=True)
class LLMResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: StopReason = "end_turn"
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMProvider(Protocol):
    name: str

    async def generate(
        self,
        *,
        system: str,
        turns: Sequence[LLMTurn],
        tools: Sequence[ToolDefinition],
    ) -> LLMResponse: ...
