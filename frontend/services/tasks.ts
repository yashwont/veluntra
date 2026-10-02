import { api } from "@/lib/api-client";
import type { Page, Task, TaskPriority, TaskStatus } from "@/lib/types";

export interface TaskQuery {
  status?: TaskStatus;
  priority?: TaskPriority;
  overdue?: boolean;
  due_before?: string;
  due_after?: string;
  limit?: number;
  offset?: number;
}

export interface TaskInput {
  title: string;
  description?: string | null;
  status?: TaskStatus;
  priority?: TaskPriority;
  due_date?: string | null;
}

const base = (workspaceId: string) => `workspaces/${workspaceId}/tasks`;

export const listTasks = (workspaceId: string, query: TaskQuery = {}) =>
  api<Page<Task>>(base(workspaceId), { query: { ...query } });

export const createTask = (workspaceId: string, input: TaskInput) =>
  api<Task>(base(workspaceId), { method: "POST", body: input });

/** Partial update: only the fields present are changed. */
export const updateTask = (workspaceId: string, taskId: string, patch: Partial<TaskInput>) =>
  api<Task>(`${base(workspaceId)}/${taskId}`, { method: "PATCH", body: patch });

export const deleteTask = (workspaceId: string, taskId: string) =>
  api<void>(`${base(workspaceId)}/${taskId}`, { method: "DELETE" });
