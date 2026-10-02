import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from app.llm.types import (
    AssistantToolTurn,
    LLMProvider,
    LLMTurn,
    TextTurn,
    ToolResult,
    ToolResultsTurn,
)
from app.tools.base import ToolContext
from app.tools.registry import ToolEvent, ToolRegistry

logger = logging.getLogger(__name__)

AgentStop = Literal["end_turn", "max_tokens", "refusal", "max_iterations"]

FALLBACK_TEXT = {
    "max_iterations": "I couldn't finish that within my step limit. Part of it may be done; "
    "please check your tasks and notes, then try a simpler request.",
    "max_tokens": "My reply was cut off. Please try asking in a smaller piece.",
    "refusal": "I can't help with that request.",
    "end_turn": "I wasn't able to produce a response. Please try again.",
}


@dataclass
class AgentResult:
    text: str
    stop_reason: AgentStop
    tool_events: list[ToolEvent] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


class Orchestrator:
    """Runs one user request to completion.

    The model decides *what* should happen; this loop only relays: it passes the
    model's tool requests to the registry (which validates and executes them via
    the application services) and returns the outcomes to the model, until the
    model answers in plain text. The model never touches the database.
    """

    def __init__(
        self, provider: LLMProvider, registry: ToolRegistry, max_iterations: int
    ) -> None:
        self.provider = provider
        self.registry = registry
        self.max_iterations = max_iterations

    async def run(
        self,
        *,
        system: str,
        turns: Sequence[TextTurn],
        ctx: ToolContext,
    ) -> AgentResult:
        """`turns` is the conversation so far, ending with the user's new message."""
        turns = list[LLMTurn](turns)
        tools = self.registry.definitions()
        events: list[ToolEvent] = []
        tokens_in = tokens_out = 0

        for _ in range(self.max_iterations):
            response = await self.provider.generate(system=system, turns=turns, tools=tools)
            tokens_in += response.input_tokens or 0
            tokens_out += response.output_tokens or 0

            if not response.tool_calls:
                stop: AgentStop
                if response.stop_reason == "max_tokens":
                    stop = "max_tokens"
                elif response.stop_reason == "refusal":
                    stop = "refusal"
                else:
                    stop = "end_turn"
                text = response.text.strip() or FALLBACK_TEXT[stop]
                return AgentResult(text, stop, events, tokens_in, tokens_out)

            # Run every requested tool, then return all results together
            results: list[ToolResult] = []
            for call in response.tool_calls:
                outcome = await self.registry.execute(call.name, call.input, ctx)
                events.append(outcome.event)
                results.append(ToolResult(call.id, outcome.content, outcome.is_error))
            turns.append(AssistantToolTurn(response.text, list(response.tool_calls)))
            turns.append(ToolResultsTurn(results))

        logger.warning("assistant hit its iteration limit", extra={"limit": self.max_iterations})
        return AgentResult(
            FALLBACK_TEXT["max_iterations"], "max_iterations", events, tokens_in, tokens_out
        )
