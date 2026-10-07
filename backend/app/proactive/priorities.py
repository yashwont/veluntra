"""Deciding which open tasks deserve attention today, and saying why.

Plain, explainable rules (not a model): a task's score comes from how close or past
its deadline is, plus how important it was marked. The reasons are shown to the user
so the ranking can be checked and trusted.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from app.models.task import Task, TaskPriority, TaskStatus

MIN_SCORE = 30  # below this a task isn't worth flagging today

_PRIORITY_SCORE = {
    TaskPriority.URGENT: 40,
    TaskPriority.HIGH: 30,
    TaskPriority.MEDIUM: 10,
    TaskPriority.LOW: 0,
}
_PRIORITY_REASON = {TaskPriority.URGENT: "Urgent priority", TaskPriority.HIGH: "High priority"}


@dataclass(frozen=True)
class RankedTask:
    task: Task
    score: int
    reason: str


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _timing(task: Task, now: datetime, tz: ZoneInfo) -> tuple[int, str | None]:
    if task.due_date is None:
        return 0, None
    due_local = task.due_date.astimezone(tz)
    days = (due_local.date() - now.astimezone(tz).date()).days  # whole calendar days
    if task.due_date < now:
        if days == 0:
            return 100, "Overdue (was due earlier today)"
        return 100 + min(30, -days), f"Overdue by {_plural(-days, 'day')}"
    if days == 0:
        return 80, "Due today"
    if days == 1:
        return 55, "Due tomorrow"
    if days <= 3:
        return 35, f"Due in {_plural(days, 'day')}"
    return 0, None


def rank_tasks(tasks: Sequence[Task], now: datetime, tz: ZoneInfo) -> list[RankedTask]:
    """Open tasks worth flagging, most pressing first."""
    ranked: list[RankedTask] = []
    for task in tasks:
        if task.status not in (TaskStatus.TODO, TaskStatus.IN_PROGRESS):
            continue
        score, timing = _timing(task, now, tz)
        score += _PRIORITY_SCORE[task.priority]
        if task.status == TaskStatus.IN_PROGRESS:
            score += 5
        if score < MIN_SCORE:
            continue
        reasons = [r for r in (timing, _PRIORITY_REASON.get(task.priority)) if r]
        ranked.append(RankedTask(task, score, " · ".join(reasons)))
    # Highest score first; ties go to the earlier deadline, then the newer task
    ranked.sort(
        key=lambda r: (
            -r.score,
            r.task.due_date or datetime.max.replace(tzinfo=now.tzinfo),
            -r.task.created_at.timestamp(),
        )
    )
    return ranked
