import uuid
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.models.task import TaskPriority, TaskStatus


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=10_000)
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: AwareDatetime | None = Field(
        default=None, description="Must include a timezone, e.g. 2026-10-05T09:00:00Z."
    )

    @model_validator(mode="after")
    def title_not_blank(self) -> "TaskCreate":
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("title must not be blank")
        return self


class TaskUpdate(BaseModel):
    """Partial update: only fields present in the request body are changed."""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=10_000)
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_date: AwareDatetime | None = None

    @model_validator(mode="after")
    def required_fields_not_null(self) -> "TaskUpdate":
        # description and due_date may be set to null (cleared); these may not
        for name in ("title", "status", "priority"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        if self.title is not None:
            self.title = self.title.strip()
            if not self.title:
                raise ValueError("title must not be blank")
        return self


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    due_date: datetime | None
    source: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
