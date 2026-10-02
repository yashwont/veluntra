import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_TAGS = 20
MAX_TAG_LENGTH = 50
MAX_CONTENT_LENGTH = 100_000


def normalize_tags(tags: list[str]) -> list[str]:
    """Lowercase, trim and de-duplicate tags, keeping first-seen order."""
    result: list[str] = []
    for raw in tags:
        tag = raw.strip().lower()
        if not tag:
            raise ValueError("tags must not be empty")
        if len(tag) > MAX_TAG_LENGTH:
            raise ValueError(f"each tag must be at most {MAX_TAG_LENGTH} characters")
        if tag not in result:
            result.append(tag)
    if len(result) > MAX_TAGS:
        raise ValueError(f"at most {MAX_TAGS} tags are allowed")
    return result


class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(default="", max_length=MAX_CONTENT_LENGTH)
    tags: list[str] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value

    _normalize_tags = field_validator("tags")(normalize_tags)


class NoteUpdate(BaseModel):
    """Partial update: only fields present in the request body are changed.

    `tags`, when sent, replaces the whole tag list.
    """

    title: str | None = Field(default=None, min_length=1, max_length=300)
    content: str | None = Field(default=None, max_length=MAX_CONTENT_LENGTH)
    tags: list[str] | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else normalize_tags(value)

    @model_validator(mode="after")
    def fields_not_null(self) -> "NoteUpdate":
        for name in ("title", "content", "tags"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class NoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    content: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class NoteSummary(BaseModel):
    """List-view note: a short preview instead of the full content."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    preview: str = Field(description="First 200 characters of the content.")
    tags: list[str]
    created_at: datetime
    updated_at: datetime
