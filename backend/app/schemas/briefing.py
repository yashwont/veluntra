import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.task import TaskPriority, TaskStatus

# Why a Google-backed section may be empty
SectionStatus = Literal["ok", "not_connected", "needs_reauth", "unavailable"]


class TaskBrief(BaseModel):
    id: uuid.UUID
    title: str
    priority: TaskPriority
    status: TaskStatus
    due_date: datetime | None


class PriorityItem(TaskBrief):
    reason: str = Field(description="Why this task is on today's list, e.g. 'Overdue by 3 days · High priority'.")


class ContextItem(BaseModel):
    type: Literal["document", "memory", "note", "task"]
    id: uuid.UUID
    title: str
    snippet: str


class MeetingBrief(BaseModel):
    id: str
    title: str
    start: datetime
    end: datetime
    all_day: bool
    location: str | None
    attendees: list[str]
    overlaps: bool = Field(description="Overlaps another event today.")
    context: list[ContextItem] = Field(description="Your own documents, notes, memories and tasks related to it.")


class FollowUp(BaseModel):
    kind: Literal["email", "task", "commitment"]
    title: str
    detail: str
    days_waiting: int


class DocumentBrief(BaseModel):
    id: uuid.UUID
    filename: str
    processed_at: datetime | None


class BriefingRead(BaseModel):
    date: date
    timezone: str
    generated_at: datetime
    priorities: list[PriorityItem] = Field(description="The few things most worth doing today, with reasons.")
    overdue: list[TaskBrief]
    due_today: list[TaskBrief]
    due_tomorrow: list[TaskBrief]
    meetings: list[MeetingBrief]
    meetings_status: SectionStatus
    follow_ups: list[FollowUp]
    follow_ups_status: SectionStatus = Field(description="Status of the email part of follow-ups.")
    recent_documents: list[DocumentBrief]
    pending_suggestions: int = Field(description="Suggested tasks waiting for your decision.")
    suggested_actions: list[str]
