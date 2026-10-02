"use client";

import { Badge } from "@/components/ui";
import { formatDue, isOverdue } from "@/lib/dates";
import { PRIORITY_LABELS, PRIORITY_TONES, STATUS_LABELS } from "@/lib/task-meta";
import type { Task } from "@/lib/types";

export function TaskRow({
  task,
  now,
  onOpen,
  onToggle,
  disabled,
}: {
  task: Task;
  now: number;
  onOpen: (task: Task) => void;
  onToggle: (task: Task) => void;
  disabled?: boolean;
}) {
  const done = task.status === "completed";
  const inactive = done || task.status === "cancelled";
  const overdue = isOverdue(task, now);

  return (
    <li className="flex items-start gap-3 px-4 py-3 hover:bg-muted/50">
      <input
        type="checkbox"
        checked={done}
        disabled={disabled || task.status === "cancelled"}
        onChange={() => onToggle(task)}
        aria-label={done ? `Reopen "${task.title}"` : `Complete "${task.title}"`}
        className="mt-1 size-4 shrink-0 cursor-pointer accent-[var(--accent)]"
      />
      <button
        type="button"
        onClick={() => onOpen(task)}
        className="min-w-0 flex-1 text-left focus-visible:outline-2 focus-visible:outline-accent"
      >
        <span className={`block truncate text-sm font-medium ${inactive ? "text-muted-foreground line-through" : ""}`}>
          {task.title}
        </span>
        {task.description && (
          <span className="mt-0.5 block truncate text-sm text-muted-foreground">{task.description}</span>
        )}
        <span className="mt-1.5 flex flex-wrap items-center gap-2">
          {!inactive && <Badge tone={PRIORITY_TONES[task.priority]}>{PRIORITY_LABELS[task.priority]}</Badge>}
          {task.status !== "todo" && task.status !== "completed" && (
            <Badge tone={task.status === "in_progress" ? "accent" : "neutral"}>{STATUS_LABELS[task.status]}</Badge>
          )}
          {task.due_date && (
            <span className={`text-xs ${overdue ? "font-medium text-danger" : "text-muted-foreground"}`}>
              {overdue ? "Overdue · " : "Due "}
              {formatDue(task.due_date)}
            </span>
          )}
        </span>
      </button>
    </li>
  );
}
