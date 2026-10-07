import uuid
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.models.suggestion import SuggestionKind, SuggestionStatus
from app.models.task import TaskPriority
from app.schemas.task import TaskRead


class SuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: SuggestionKind
    title: str
    description: str | None
    priority: TaskPriority
    due_date: datetime | None
    reason: str = Field(description="Why this was suggested.")
    confidence: float | None = Field(description="0 to 1: how sure the detector is; null if not applicable.")
    source_type: str
    source_label: str | None = Field(description="Subject of the email it came from.")
    status: SuggestionStatus
    task_id: uuid.UUID | None = Field(description="The task created when accepted.")
    created_at: datetime


class SuggestionAccept(BaseModel):
    """Optional tweaks applied when accepting: anything omitted keeps the suggested value."""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    priority: TaskPriority | None = None
    due_date: AwareDatetime | None = None


class SuggestionAccepted(BaseModel):
    suggestion: SuggestionRead
    task: TaskRead


class ScanResult(BaseModel):
    created: int = Field(description="How many new suggestions this scan found.")
    pending: list[SuggestionRead] = Field(description="Everything now waiting for your decision.")
