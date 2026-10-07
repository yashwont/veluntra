"""The assistant's model, running locally through Ollama (LLM_PROVIDER=ollama).

Free and private: nothing leaves the computer. Translates the app's provider-neutral
turns (`app.llm.types`) to Ollama's /api/chat format and back; everything else
(validation, tools, storage) is the same code that runs with the demo model.

Ollama's tool calling works with models trained for it (llama3.1/3.2, qwen2.5,
mistral-nemo...). Their output is untrusted exactly like any other model's: the tool
registry checks every call against a strict schema before anything runs.
"""

import json
import logging
import uuid
from collections.abc import Sequence
from typing import Any

import httpx

from app.core.config import get_settings
from app.integrations.ollama import OllamaClient, OllamaError
from app.llm.errors import LLMError
from app.llm.types import (
    AssistantToolTurn,
    LLMResponse,
    LLMTurn,
    TextTurn,
    ToolCall,
    ToolDefinition,
    ToolResultsTurn,
)

logger = logging.getLogger(__name__)

_MAX_REF_DEPTH = 8


def simplify_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Make a Pydantic JSON Schema easy for a small model to read.

    Pydantic emits `$defs`/`$ref` indirection, `title` noise and `anyOf [X, null]` for
    optional fields. Large models cope; small local ones often don't, and the noise also
    eats context. This inlines references, drops titles and collapses optionals. The
    result describes the same arguments, and validation still uses the original schema.
    """
    defs = schema.get("$defs", {})

    def walk(node: Any, depth: int) -> Any:
        if isinstance(node, list):
            return [walk(item, depth) for item in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node and depth < _MAX_REF_DEPTH:
            target = defs.get(node["$ref"].rsplit("/", 1)[-1], {})
            extra = {k: v for k, v in node.items() if k != "$ref"}
            return walk({**target, **extra}, depth + 1)
        if "anyOf" in node:
            options = [o for o in node["anyOf"] if o.get("type") != "null"]
            if len(options) == 1:  # Optional[X]: whether it's required is in `required`
                rest = {k: v for k, v in node.items() if k != "anyOf"}
                return walk({**options[0], **rest}, depth)
        result: dict[str, Any] = {}
        for key, value in node.items():
            if key in ("title", "$defs"):
                continue  # annotation noise, not part of what the arguments are
            if key == "properties" and isinstance(value, dict):
                # These keys are *argument names* (a tool may well have one called "title"):
                # keep every name and simplify only each argument's own schema
                result[key] = {name: walk(sub, depth) for name, sub in value.items()}
            else:
                result[key] = walk(value, depth)
        return result

    return walk(schema, 0)


def _tool_payload(tool: ToolDefinition) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": simplify_schema(tool.input_schema),
        },
    }


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        num_ctx: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        settings = get_settings()
        self.model = model or settings.ollama_model
        self.num_ctx = num_ctx or settings.ollama_num_ctx
        self.client = OllamaClient(
            base_url or settings.ollama_base_url,
            timeout or settings.ollama_timeout_seconds,
            transport,
        )

    # --- app turns -> Ollama messages ---------------------------------------------

    @staticmethod
    def _messages(system: str, turns: Sequence[LLMTurn]) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        tool_names: dict[str, str] = {}  # call id -> tool name, to label the results
        for turn in turns:
            if isinstance(turn, TextTurn):
                messages.append({"role": turn.role, "content": turn.text})
            elif isinstance(turn, AssistantToolTurn):
                tool_names.update({call.id: call.name for call in turn.tool_calls})
                messages.append(
                    {
                        "role": "assistant",
                        "content": turn.text,
                        "tool_calls": [
                            {"function": {"name": call.name, "arguments": call.input}}
                            for call in turn.tool_calls
                        ],
                    }
                )
            elif isinstance(turn, ToolResultsTurn):
                for result in turn.results:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_name": tool_names.get(result.tool_call_id, ""),
                            "content": result.content,
                        }
                    )
        return messages

    # --- the call -------------------------------------------------------------------

    async def generate(
        self,
        *,
        system: str,
        turns: Sequence[LLMTurn],
        tools: Sequence[ToolDefinition],
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._messages(system, turns),
            "stream": False,
            # Low temperature: tool arguments should be precise, not creative
            "options": {"temperature": 0.2, "num_ctx": self.num_ctx},
        }
        if tools:
            payload["tools"] = [_tool_payload(t) for t in tools]

        try:
            data = await self.client.post("/api/chat", payload, model=self.model)
        except OllamaError as exc:
            logger.error("ollama chat failed", extra={"reason": str(exc), "model": self.model})
            raise LLMError(str(exc)) from exc

        message = data.get("message")
        if not isinstance(message, dict):
            raise LLMError("Ollama's reply had no message.")

        calls = self._tool_calls(message)
        content = message.get("content")
        text = content if isinstance(content, str) else ""
        if calls:
            stop = "tool_use"
        elif data.get("done_reason") == "length":
            stop = "max_tokens"
        else:
            stop = "end_turn"
        return LLMResponse(
            text=text,
            tool_calls=calls,
            stop_reason=stop,
            input_tokens=_count(data.get("prompt_eval_count")),
            output_tokens=_count(data.get("eval_count")),
        )

    @staticmethod
    def _tool_calls(message: dict[str, Any]) -> list[ToolCall]:
        calls: list[ToolCall] = []
        for item in message.get("tool_calls") or []:
            function = item.get("function") if isinstance(item, dict) else None
            if not isinstance(function, dict) or not isinstance(function.get("name"), str):
                continue
            arguments = function.get("arguments")
            if isinstance(arguments, str):  # some versions send the arguments as JSON text
                try:
                    arguments = json.loads(arguments)
                except ValueError:
                    arguments = {}
            if not isinstance(arguments, dict):
                arguments = {}
            # Ollama doesn't give calls ids; the app needs one to pair results with calls
            calls.append(
                ToolCall(id=f"ollama_{uuid.uuid4().hex[:12]}", name=function["name"], input=arguments)
            )
        return calls


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
