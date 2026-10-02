import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.task import Task, TaskStatus
from app.repositories.tasks import TaskFilters, TaskRepository
from app.schemas.task import TaskCreate, TaskUpdate

logger = logging.getLogger(__name__)


class TaskNotFoundError(NotFoundError):
    code = "TASK_NOT_FOUND"
    message = "The requested task does not exist."


class TaskService:
    """Business logic for tasks within one workspace.

    The caller (route or, later, an AI tool) must already have verified the user
    belongs to `workspace_id`; this service guarantees it never touches any
    other workspace's tasks.
    """

    def __init__(self, session: AsyncSession, workspace_id: uuid.UUID) -> None:
        self.session = session
        self.workspace_id = workspace_id
        self.tasks = TaskRepository(session)

    async def create(self, data: TaskCreate, source: str = "manual") -> Task:
        task = Task(
            workspace_id=self.workspace_id,
            title=data.title,
            description=data.description,
            status=data.status,
            priority=data.priority,
            due_date=data.due_date,
            source=source,
            completed_at=_now() if data.status == TaskStatus.COMPLETED else None,
        )
        self.tasks.add(task)
        await self.session.commit()
        await self.session.refresh(task)  # load server-generated columns
        logger.info(
            "task created",
            extra={"task_id": str(task.id), "workspace_id": str(self.workspace_id)},
        )
        return task

    async def get(self, task_id: uuid.UUID) -> Task:
        task = await self.tasks.get(self.workspace_id, task_id)
        if task is None:
            raise TaskNotFoundError()
        return task

    async def list(
        self, filters: TaskFilters, limit: int, offset: int
    ) -> tuple[list[Task], int]:
        return await self.tasks.list(self.workspace_id, filters, limit, offset)

    async def update(self, task_id: uuid.UUID, data: TaskUpdate) -> Task:
        task = await self.get(task_id)
        changes = data.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(task, field, value)

        if "status" in changes:
            # completed_at always mirrors whether the task is completed
            if task.status == TaskStatus.COMPLETED:
                task.completed_at = task.completed_at or _now()
            else:
                task.completed_at = None

        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def delete(self, task_id: uuid.UUID) -> None:
        task = await self.get(task_id)
        await self.tasks.delete(task)
        await self.session.commit()
        logger.info(
            "task deleted",
            extra={"task_id": str(task_id), "workspace_id": str(self.workspace_id)},
        )


def _now() -> datetime:
    return datetime.now(timezone.utc)
