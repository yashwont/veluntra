import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.memory import MemoryKind
from app.models.task import TaskPriority, TaskStatus
from app.services.search_service import SearchType


class SearchResultRead(BaseModel):
    type: SearchType
    id: uuid.UUID = Field(description="Id of the task, note, document or memory.")
    title: str
    snippet: str = Field(description="Short excerpt: description, preview, matching passage or content.")
    score: float | None = Field(
        description="Relevance from 0 to 1 (higher is better); null when results are filter-only."
    )
    updated_at: datetime
    # Type-specific details, present only for the types they belong to
    tags: list[str] | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_date: datetime | None = None
    kind: MemoryKind | None = None


class AppliedFilters(BaseModel):
    """What the search understood from the query, so the UI can show it."""

    text: str
    types: list[SearchType]
    tags: list[str]
    status: TaskStatus | None
    priority: TaskPriority | None
    overdue: bool | None
    kind: MemoryKind | None


class SearchResponse(BaseModel):
    applied: AppliedFilters
    results: list[SearchResultRead]
