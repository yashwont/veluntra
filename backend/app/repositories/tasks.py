import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import false, func, not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task, TaskPriority, TaskStatus

_OPEN_STATUSES = (TaskStatus.TODO, TaskStatus.IN_PROGRESS)


@dataclass
class TaskFilters:
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_before: datetime | None = None
    due_after: datetime | None = None
    overdue: bool | None = None


class TaskRepository:
    """Task data access. Every method takes workspace_id and filters on it,
    so a task can never be reached from outside its workspace."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, task: Task) -> None:
        self.session.add(task)

    async def get(self, workspace_id: uuid.UUID, task_id: uuid.UUID) -> Task | None:
        result = await self.session.execute(
            select(Task).where(Task.id == task_id, Task.workspace_id == workspace_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        workspace_id: uuid.UUID,
        filters: TaskFilters,
        limit: int,
        offset: int,
    ) -> tuple[list[Task], int]:
        conditions = [Task.workspace_id == workspace_id]
        if filters.status is not None:
            conditions.append(Task.status == filters.status)
        if filters.priority is not None:
            conditions.append(Task.priority == filters.priority)
        if filters.due_before is not None:
            conditions.append(Task.due_date <= filters.due_before)
        if filters.due_after is not None:
            conditions.append(Task.due_date >= filters.due_after)
        if filters.overdue is not None:
            # coalesce: an undated task compares as NULL, which must count as
            # "not overdue" (NOT NULL is NULL and would wrongly drop the row)
            is_overdue = func.coalesce(
                (Task.due_date < datetime.now(timezone.utc))
                & Task.status.in_(_OPEN_STATUSES),
                false(),
            )
            conditions.append(is_overdue if filters.overdue else not_(is_overdue))

        total = await self.session.scalar(
            select(func.count()).select_from(Task).where(*conditions)
        )
        result = await self.session.execute(
            select(Task)
            .where(*conditions)
            # Soonest deadline first, undated tasks last; id makes paging stable
            .order_by(Task.due_date.asc().nulls_last(), Task.created_at.desc(), Task.id)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars()), total or 0

    async def delete(self, task: Task) -> None:
        await self.session.delete(task)
