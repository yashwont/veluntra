"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useWorkspace } from "@/hooks/use-workspace";
import {
  type TaskInput,
  type TaskQuery,
  createTask,
  deleteTask,
  listTasks,
  updateTask,
} from "@/services/tasks";

export function useTasks(query: TaskQuery, options: { enabled?: boolean } = {}) {
  const { workspaceId } = useWorkspace();
  return useQuery({
    queryKey: ["tasks", workspaceId, query],
    queryFn: () => listTasks(workspaceId!, query),
    enabled: !!workspaceId && (options.enabled ?? true),
    placeholderData: keepPreviousData, // no flicker while filters/pages change
  });
}

export function useTaskMutations() {
  const { workspaceId } = useWorkspace();
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["tasks", workspaceId] });

  return {
    create: useMutation({
      mutationFn: (input: TaskInput) => createTask(workspaceId!, input),
      onSuccess: refresh,
    }),
    update: useMutation({
      mutationFn: ({ id, patch }: { id: string; patch: Partial<TaskInput> }) =>
        updateTask(workspaceId!, id, patch),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: string) => deleteTask(workspaceId!, id),
      onSuccess: refresh,
    }),
  };
}
