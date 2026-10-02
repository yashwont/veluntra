"use client";

import { useState } from "react";

import { Button, ErrorBanner, Field, Input, Select, Textarea } from "@/components/ui";
import { useTaskMutations } from "@/hooks/use-tasks";
import { ApiError } from "@/lib/api-client";
import { endOfDayIso, toDateInput } from "@/lib/dates";
import { PRIORITY_LABELS, STATUS_LABELS } from "@/lib/task-meta";
import {
  TASK_PRIORITIES,
  TASK_STATUSES,
  type Task,
  type TaskPriority,
  type TaskStatus,
} from "@/lib/types";

/** Create (no `task`) or edit (`task`) form. Rendered inside a Modal. */
export function TaskForm({ task, onDone }: { task?: Task; onDone: () => void }) {
  const { create, update, remove } = useTaskMutations();

  const initialDue = task?.due_date ? toDateInput(task.due_date) : "";
  const [title, setTitle] = useState(task?.title ?? "");
  const [description, setDescription] = useState(task?.description ?? "");
  const [status, setStatus] = useState<TaskStatus>(task?.status ?? "todo");
  const [priority, setPriority] = useState<TaskPriority>(task?.priority ?? "medium");
  const [dueDate, setDueDate] = useState(initialDue);

  const mutation = task ? update : create;
  const error = mutation.error instanceof ApiError ? mutation.error : null;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const fields = {
      title,
      description: description.trim() || null,
      status,
      priority,
      // Untouched dates are left alone, so a task's exact due time isn't rewritten
      ...(dueDate !== initialDue && { due_date: dueDate ? endOfDayIso(dueDate) : null }),
    };
    if (task) {
      update.mutate({ id: task.id, patch: fields }, { onSuccess: onDone });
    } else {
      create.mutate(fields, { onSuccess: onDone });
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <Field label="Title" htmlFor="task-title" error={error?.fieldError("title")}>
        <Input
          id="task-title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={300}
          required
          autoFocus
        />
      </Field>
      <Field label="Description" htmlFor="task-description" error={error?.fieldError("description")}>
        <Textarea
          id="task-description"
          rows={3}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Status" htmlFor="task-status">
          <Select
            id="task-status"
            className="w-full"
            value={status}
            onChange={(e) => setStatus(e.target.value as TaskStatus)}
          >
            {TASK_STATUSES.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABELS[s]}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Priority" htmlFor="task-priority">
          <Select
            id="task-priority"
            className="w-full"
            value={priority}
            onChange={(e) => setPriority(e.target.value as TaskPriority)}
          >
            {TASK_PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {PRIORITY_LABELS[p]}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <Field label="Due date" htmlFor="task-due" error={error?.fieldError("due_date")}>
        <Input id="task-due" type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
      </Field>

      {!error?.details.length && <ErrorBanner error={mutation.error ?? remove.error} />}

      <div className="flex items-center gap-2 pt-2">
        {task && (
          <Button
            variant="danger"
            disabled={remove.isPending}
            onClick={() => {
              if (confirm(`Delete "${task.title}"? This can't be undone.`)) {
                remove.mutate(task.id, { onSuccess: onDone });
              }
            }}
          >
            Delete
          </Button>
        )}
        <div className="ml-auto flex gap-2">
          <Button variant="secondary" onClick={onDone}>
            Cancel
          </Button>
          <Button type="submit" disabled={mutation.isPending || !title.trim()}>
            {mutation.isPending ? "Saving…" : task ? "Save changes" : "Create task"}
          </Button>
        </div>
      </div>
    </form>
  );
}
