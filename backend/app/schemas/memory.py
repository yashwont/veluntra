import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.memory import MemoryKind, MemorySource

MAX_CONTENT_LENGTH = 1000
MAX_SUBJECT_LENGTH = 200


def _clean_subject(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class MemoryCreate(BaseModel):
    """A memory written by the user. (Assistant-written ones go through the tool.)"""

    content: str = Field(min_length=1, max_length=MAX_CONTENT_LENGTH)
    kind: MemoryKind = MemoryKind.FACT
    subject: str | None = Field(default=None, max_length=MAX_SUBJECT_LENGTH)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content must not be blank")
        return value

    _clean_subject = field_validator("subject")(_clean_subject)


class MemoryUpdate(BaseModel):
    """Partial update: only fields present in the request body are changed."""

    content: str | None = Field(default=None, min_length=1, max_length=MAX_CONTENT_LENGTH)
    kind: MemoryKind | None = None
    subject: str | None = Field(default=None, max_length=MAX_SUBJECT_LENGTH)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("content must not be blank")
        return value

    _clean_subject = field_validator("subject")(_clean_subject)

    @model_validator(mode="after")
    def required_fields_not_null(self) -> "MemoryUpdate":
        for name in ("content", "kind"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class MemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    kind: MemoryKind
    content: str
    subject: str | None
    source_type: MemorySource = Field(description="Where the memory came from.")
    source_id: uuid.UUID | None
    source_label: str | None = Field(description="Title of the source when it was remembered.")
    confidence: float | None
    extraction: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class MemorySearchHit(BaseModel):
    memory: MemoryRead
    score: float = Field(description="Cosine similarity to the query; higher is closer.")
