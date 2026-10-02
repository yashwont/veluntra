"use client";

import { useState } from "react";

import { TaskForm } from "@/components/tasks/task-form";
import { TaskRow } from "@/components/tasks/task-row";
import { Button, EmptyState, ErrorBanner, Input, Modal, Select, Spinner } from "@/components/ui";
import { useNow } from "@/hooks/use-now";
import { useTaskMutations, useTasks } from "@/hooks/use-tasks";
import { STATUS_LABELS, PRIORITY_LABELS } from "@/lib/task-meta";
import { TASK_PRIORITIES, TASK_STATUSES, type Task, type TaskPriority, type TaskStatus } from "@/lib/types";

const PAGE_SIZE = 20;

export default function TasksPage() {
  const now = useNow();
  const [status, setStatus] = useState<TaskStatus | undefined>();
  const [priority, setPriority] = useState<TaskPriority | undefined>();
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [offset, setOffset] = useState(0);
  const [editing, setEditing] = useState<Task | "new" | null>(null);
  const [quickTitle, setQuickTitle] = useState("");

  const { create, update } = useTaskMutations();
  const tasks = useTasks({
    status,
    priority,
    overdue: overdueOnly || undefined,
    limit: PAGE_SIZE,
    offset,
  });

  // Any filter change goes back to the first page
  const withReset = <T,>(setter: (value: T) => void) => (value: T) => {
    setter(value);
    setOffset(0);
  };

  const total = tasks.data?.total ?? 0;
  const items = tasks.data?.items ?? [];
  const filtered = !!status || !!priority || overdueOnly;

  function quickAdd(e: React.FormEvent) {
    e.preventDefault();
    const title = quickTitle.trim();
    if (!title) return;
    create.mutate({ title }, { onSuccess: () => setQuickTitle("") });
  }

  function toggle(task: Task) {
    update.mutate({
      id: task.id,
      patch: { status: task.status === "completed" ? "todo" : "completed" },
    });
  }

  return (
    <>
      <div className="mb-6 flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">Tasks</h1>
        <Button onClick={() => setEditing("new")}>New task</Button>
      </div>

      <form onSubmit={quickAdd} className="mb-4 flex gap-2">
        <Input
          value={quickTitle}
          onChange={(e) => setQuickTitle(e.target.value)}
          placeholder="Add a task and press Enter"
          aria-label="Quick add task"
          maxLength={300}
        />
        <Button type="submit" variant="secondary" disabled={create.isPending || !quickTitle.trim()}>
          Add
        </Button>
      </form>
      <ErrorBanner error={create.error ?? update.error} />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Select
          aria-label="Filter by status"
          value={status ?? ""}
          onChange={(e) => withReset(setStatus)((e.target.value || undefined) as TaskStatus | undefined)}
        >
          <option value="">All statuses</option>
          {TASK_STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABELS[s]}
            </option>
          ))}
        </Select>
        <Select
          aria-label="Filter by priority"
          value={priority ?? ""}
          onChange={(e) => withReset(setPriority)((e.target.value || undefined) as TaskPriority | undefined)}
        >
          <option value="">All priorities</option>
          {TASK_PRIORITIES.map((p) => (
            <option key={p} value={p}>
              {PRIORITY_LABELS[p]}
            </option>
          ))}
        </Select>
        <Button
          variant={overdueOnly ? "primary" : "secondary"}
          aria-pressed={overdueOnly}
          onClick={() => withReset(setOverdueOnly)(!overdueOnly)}
        >
          Overdue
        </Button>
        {filtered && (
          <Button
            variant="ghost"
            onClick={() => {
              setStatus(undefined);
              setPriority(undefined);
              setOverdueOnly(false);
              setOffset(0);
            }}
          >
            Clear filters
          </Button>
        )}
      </div>

      {tasks.isLoading ? (
        <Spinner />
      ) : tasks.error ? (
        <ErrorBanner error={tasks.error} />
      ) : items.length === 0 ? (
        <EmptyState
          title={filtered ? "No tasks match these filters" : "No tasks yet"}
          description={filtered ? undefined : "Add your first task above to get started."}
          action={
            offset > 0 ? (
              <Button variant="secondary" onClick={() => setOffset(0)}>
                Back to first page
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
          <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
            {items.map((task) => (
              <TaskRow
                key={task.id}
                task={task}
                now={now}
                onOpen={setEditing}
                onToggle={toggle}
                disabled={update.isPending}
              />
            ))}
          </ul>

          <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
            <span>
              {offset + 1}–{offset + items.length} of {total}
            </span>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                Previous
              </Button>
              <Button
                variant="secondary"
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}

      <Modal
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "New task" : "Edit task"}
      >
        {editing !== null && (
          <TaskForm
            key={editing === "new" ? "new" : editing.id}
            task={editing === "new" ? undefined : editing}
            onDone={() => setEditing(null)}
          />
        )}
      </Modal>
    </>
  );
}
