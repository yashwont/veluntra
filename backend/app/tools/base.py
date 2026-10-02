import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ToolContext:
    """Who is acting, and where. Built by the server from the authenticated,
    authorized request. The model never supplies or influences any of this."""

    session: AsyncSession
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    timezone: ZoneInfo

    def end_of_day(self, day: date) -> datetime:
        """A due *date* means the end of that day in the user's timezone."""
        return datetime.combine(day, time(23, 59, 59), tzinfo=self.timezone)

    def start_of_day(self, day: date) -> datetime:
        return datetime.combine(day, time.min, tzinfo=self.timezone)

    def local_date(self, moment: datetime) -> date:
        return moment.astimezone(self.timezone).date()


Handler = Callable[[ToolContext, Any], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class Tool:
    """A capability the model may request.

    `input_model` is the contract for the model's arguments: strict (unknown
    fields are rejected) and validated before `handler` runs. The handler calls
    the application's services, the same code paths the REST API uses, so every
    existing rule and workspace scoping applies unchanged.
    """

    name: str
    description: str
    input_model: type[BaseModel]
    handler: Handler
