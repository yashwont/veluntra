import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.conversation import MessageRole

MAX_MESSAGE_LENGTH = 4000


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)
    conversation_id: uuid.UUID | None = Field(
        default=None, description="Continue this conversation. Omit to start a new one."
    )
    timezone: str = Field(
        default="UTC",
        max_length=64,
        description="The user's IANA timezone, e.g. Asia/Kathmandu. Used to resolve 'tomorrow'.",
    )

    @field_validator("message")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            raise ValueError("unknown timezone") from None
        return value


class ToolEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    input: dict[str, Any]
    ok: bool
    result: dict[str, Any] | None = None
    error: str | None = None


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: MessageRole
    content: str
    tool_events: list[ToolEventRead]
    provider: str | None = Field(default=None, description="Which model backend wrote this reply.")
    created_at: datetime


class AssistantStatus(BaseModel):
    provider: str
    demo: bool = Field(description="True when running the built-in demo model instead of a real AI model.")


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    message: MessageRead
    provider: str = Field(description="Which model backend answered, e.g. 'fake' (demo) or a real provider.")


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationRead):
    messages: list[MessageRead]
