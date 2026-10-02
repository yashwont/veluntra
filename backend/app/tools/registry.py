import json
import logging
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.core.errors import AppError
from app.llm.types import ToolDefinition
from app.tools.base import Tool, ToolContext

logger = logging.getLogger(__name__)

# Hard cap on what one tool result may feed back into the model's context
MAX_RESULT_CHARS = 20_000


@dataclass(frozen=True)
class ToolEvent:
    """Record of one tool call: shown in the UI and stored for audit."""

    name: str
    input: dict[str, Any]
    ok: bool
    result: dict[str, Any] | None = None
    error: str | None = None


@dataclass(frozen=True)
class ToolOutcome:
    event: ToolEvent
    content: str  # JSON text returned to the model
    is_error: bool


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {t.name: t for t in tools}

    def definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name=t.name,
                description=t.description,
                input_schema=t.input_model.model_json_schema(),
            )
            for t in self._tools.values()
        ]

    async def execute(self, name: str, raw_input: Any, ctx: ToolContext) -> ToolOutcome:
        """Run a model-requested tool call.

        The model's output is untrusted input: the tool name must be registered
        and the arguments must validate against the tool's strict schema. Every
        failure becomes an error result the model can read and react to; none is
        ever reported as success, and none crashes the request.
        """
        arguments = raw_input if isinstance(raw_input, dict) else {}

        tool = self._tools.get(name)
        if tool is None:
            return self._failure(name, arguments, f"Unknown tool '{name}'.")

        try:
            parsed = tool.input_model.model_validate(arguments)
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(str(p) for p in e['loc']) or 'input'}: {e['msg']}"
                for e in exc.errors()
            )
            return self._failure(name, arguments, f"Invalid arguments: {problems}")

        try:
            result = await tool.handler(ctx, parsed)
        except AppError as exc:
            # Expected, user-presentable failure (e.g. not found)
            await ctx.session.rollback()
            return self._failure(name, arguments, exc.message)
        except Exception:
            # Unexpected: log the detail, tell the model only that it failed
            logger.exception(
                "tool failed",
                extra={"tool": name, "workspace_id": str(ctx.workspace_id)},
            )
            await ctx.session.rollback()
            return self._failure(name, arguments, "The tool failed unexpectedly.")

        content = json.dumps({"ok": True, **result}, default=str)
        if len(content) > MAX_RESULT_CHARS:
            return self._failure(name, arguments, "The result was too large to return.")

        logger.info(
            "tool executed",
            extra={"tool": name, "workspace_id": str(ctx.workspace_id), "ok": True},
        )
        return ToolOutcome(
            event=ToolEvent(name=name, input=arguments, ok=True, result=result),
            content=content,
            is_error=False,
        )

    @staticmethod
    def _failure(name: str, arguments: dict[str, Any], message: str) -> ToolOutcome:
        logger.warning("tool call rejected", extra={"tool": name, "reason": message})
        return ToolOutcome(
            event=ToolEvent(name=name, input=arguments, ok=False, error=message),
            content=json.dumps({"ok": False, "error": message}),
            is_error=True,
        )
