import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_membership
from app.db.session import get_session
from app.models.task import TaskPriority, TaskStatus
from app.models.workspace import WorkspaceMember
from app.repositories.tasks import TaskFilters
from app.schemas.common import Page
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate
from app.services.task_service import TaskService

router = APIRouter(prefix="/workspaces/{workspace_id}/tasks", tags=["tasks"])


async def get_task_service(
    workspace_id: uuid.UUID,
    _membership: WorkspaceMember = Depends(get_workspace_membership),
    session: AsyncSession = Depends(get_session),
) -> TaskService:
    """Builds a TaskService bound to the workspace, after authorizing access."""
    return TaskService(session, workspace_id)


@router.post(
    "", response_model=TaskRead, status_code=status.HTTP_201_CREATED, summary="Create a task"
)
async def create_task(
    body: TaskCreate, service: TaskService = Depends(get_task_service)
) -> TaskRead:
    return TaskRead.model_validate(await service.create(body))


@router.get("", response_model=Page[TaskRead], summary="List tasks")
async def list_tasks(
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    due_before: AwareDatetime | None = Query(None, description="Due on or before."),
    due_after: AwareDatetime | None = Query(None, description="Due on or after."),
    overdue: bool | None = Query(
        None,
        description="true: past due and still open (todo/in_progress). false: everything else.",
    ),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: TaskService = Depends(get_task_service),
) -> Page[TaskRead]:
    """Sorted by soonest due date (undated last), then newest first."""
    filters = TaskFilters(
        status=status,
        priority=priority,
        due_before=due_before,
        due_after=due_after,
        overdue=overdue,
    )
    tasks, total = await service.list(filters, limit, offset)
    return Page[TaskRead](
        items=[TaskRead.model_validate(t) for t in tasks],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{task_id}", response_model=TaskRead, summary="Get a task")
async def get_task(
    task_id: uuid.UUID, service: TaskService = Depends(get_task_service)
) -> TaskRead:
    return TaskRead.model_validate(await service.get(task_id))


@router.patch("/{task_id}", response_model=TaskRead, summary="Update a task")
async def update_task(
    task_id: uuid.UUID,
    body: TaskUpdate,
    service: TaskService = Depends(get_task_service),
) -> TaskRead:
    """Partial update. Send `null` for `description` or `due_date` to clear them."""
    return TaskRead.model_validate(await service.update(task_id, body))


@router.delete(
    "/{task_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a task"
)
async def delete_task(
    task_id: uuid.UUID, service: TaskService = Depends(get_task_service)
) -> Response:
    await service.delete(task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
