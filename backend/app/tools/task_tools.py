from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.task import TaskPriority, TaskStatus
from app.repositories.tasks import TaskFilters
from app.schemas.task import TaskCreate
from app.services.task_service import TaskService
from app.tools.base import Tool, ToolContext

DUE_DATE_HELP = "A calendar date, YYYY-MM-DD, in the user's timezone."


class CreateTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")  # unknown fields (e.g. workspace_id) are rejected

    title: str = Field(min_length=1, max_length=300, description="Short task title.")
    description: str | None = Field(default=None, max_length=10_000)
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM)
    due_date: date | None = Field(default=None, description=DUE_DATE_HELP + " Omit if there is no deadline.")


class SearchTasksInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    overdue: bool | None = Field(
        default=None,
        description="true: only open tasks already past their due date.",
    )
    due_before: date | None = Field(default=None, description="Due on or before. " + DUE_DATE_HELP)
    due_after: date | None = Field(default=None, description="Due on or after. " + DUE_DATE_HELP)
    limit: int = Field(default=10, ge=1, le=25)


def _task_summary(task: Any, ctx: ToolContext) -> dict[str, Any]:
    return {
        "id": str(task.id),
        "title": task.title,
        "status": task.status.value,
        "priority": task.priority.value,
        "due_date": ctx.local_date(task.due_date).isoformat() if task.due_date else None,
    }


async def create_task(ctx: ToolContext, args: CreateTaskInput) -> dict[str, Any]:
    service = TaskService(ctx.session, ctx.workspace_id)
    task = await service.create(
        TaskCreate(
            title=args.title,
            description=args.description,
            priority=args.priority,
            due_date=ctx.end_of_day(args.due_date) if args.due_date else None,
        ),
        source="assistant",
    )
    return {"task": _task_summary(task, ctx)}


async def search_tasks(ctx: ToolContext, args: SearchTasksInput) -> dict[str, Any]:
    service = TaskService(ctx.session, ctx.workspace_id)
    tasks, total = await service.list(
        TaskFilters(
            status=args.status,
            priority=args.priority,
            overdue=args.overdue,
            due_before=ctx.end_of_day(args.due_before) if args.due_before else None,
            due_after=ctx.start_of_day(args.due_after) if args.due_after else None,
        ),
        limit=args.limit,
        offset=0,
    )
    return {"total": total, "tasks": [_task_summary(t, ctx) for t in tasks]}


TASK_TOOLS = [
    Tool(
        name="create_task",
        description=(
            "Create a task for the user. Use when they ask to add a task, or to be "
            "reminded to do something. Convert relative dates ('tomorrow', 'next "
            "Monday') to a YYYY-MM-DD date using the current date given in the system prompt."
        ),
        input_model=CreateTaskInput,
        handler=create_task,
    ),
    Tool(
        name="search_tasks",
        description=(
            "Find the user's tasks, optionally filtered by status, priority, due "
            "date range, or overdue. Returns up to `limit` tasks plus the total match count."
        ),
        input_model=SearchTasksInput,
        handler=search_tasks,
    ),
]
