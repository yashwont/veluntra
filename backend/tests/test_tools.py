"""The tool registry in isolation: model output is untrusted input."""

import json
import uuid
from zoneinfo import ZoneInfo

import pytest
from pydantic import BaseModel, ConfigDict

from app.core.errors import NotFoundError
from app.db.session import SessionLocal
from app.tools.base import Tool, ToolContext
from app.tools.registry import MAX_RESULT_CHARS, ToolRegistry


class EchoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str


async def echo(ctx: ToolContext, args: EchoInput) -> dict:
    return {"echo": args.text}


async def explode(ctx: ToolContext, args: EchoInput) -> dict:
    raise RuntimeError("secret internal detail: password=hunter2")


async def not_found(ctx: ToolContext, args: EchoInput) -> dict:
    raise NotFoundError("That thing does not exist.")


async def huge(ctx: ToolContext, args: EchoInput) -> dict:
    return {"blob": "x" * (MAX_RESULT_CHARS + 1)}


REGISTRY = ToolRegistry(
    [
        Tool("echo", "Echo text.", EchoInput, echo),
        Tool("explode", "Always crashes.", EchoInput, explode),
        Tool("not_found", "Always 404s.", EchoInput, not_found),
        Tool("huge", "Returns too much.", EchoInput, huge),
    ]
)


@pytest.fixture
async def ctx():
    async with SessionLocal() as session:
        yield ToolContext(
            session=session,
            workspace_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            timezone=ZoneInfo("UTC"),
        )


async def test_valid_call_succeeds(ctx) -> None:
    outcome = await REGISTRY.execute("echo", {"text": "hi"}, ctx)

    assert outcome.event.ok and not outcome.is_error
    assert json.loads(outcome.content) == {"ok": True, "echo": "hi"}


async def test_unknown_tool_is_an_error_not_a_crash(ctx) -> None:
    outcome = await REGISTRY.execute("drop_database", {}, ctx)

    assert not outcome.event.ok and outcome.is_error
    assert "Unknown tool" in outcome.event.error


@pytest.mark.parametrize("bad_input", [{}, {"text": 5}, {"text": "x", "workspace_id": "abc"}, "not a dict", None, []])
async def test_invalid_arguments_are_rejected(ctx, bad_input) -> None:
    outcome = await REGISTRY.execute("echo", bad_input, ctx)

    assert not outcome.event.ok and outcome.is_error
    assert json.loads(outcome.content)["ok"] is False


async def test_unexpected_exception_is_reported_without_leaking_details(ctx) -> None:
    outcome = await REGISTRY.execute("explode", {"text": "x"}, ctx)

    assert not outcome.event.ok
    assert "hunter2" not in outcome.content and "hunter2" not in (outcome.event.error or "")
    assert "failed unexpectedly" in outcome.event.error


async def test_expected_app_errors_pass_their_message_through(ctx) -> None:
    outcome = await REGISTRY.execute("not_found", {"text": "x"}, ctx)

    assert not outcome.event.ok
    assert outcome.event.error == "That thing does not exist."


async def test_oversized_results_are_refused(ctx) -> None:
    outcome = await REGISTRY.execute("huge", {"text": "x"}, ctx)

    assert not outcome.event.ok
    assert len(outcome.content) < 200


def test_definitions_expose_strict_json_schemas() -> None:
    definitions = {d.name: d for d in REGISTRY.definitions()}

    schema = definitions["echo"].input_schema
    assert schema["properties"]["text"]["type"] == "string"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["text"]
