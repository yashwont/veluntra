"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useWorkspace } from "@/hooks/use-workspace";
import type { MemoryKind } from "@/lib/types";
import {
  type MemoryInput,
  type MemoryQuery,
  createMemory,
  deleteMemory,
  listMemories,
  searchMemories,
  updateMemory,
} from "@/services/memories";

export function useMemories(query: MemoryQuery) {
  const { workspaceId } = useWorkspace();
  return useQuery({
    queryKey: ["memories", workspaceId, "list", query],
    queryFn: () => listMemories(workspaceId!, query),
    enabled: !!workspaceId,
    placeholderData: keepPreviousData,
  });
}

export function useMemorySearch(q: string, kind?: MemoryKind) {
  const { workspaceId } = useWorkspace();
  return useQuery({
    queryKey: ["memories", workspaceId, "search", q, kind],
    queryFn: () => searchMemories(workspaceId!, q, kind),
    enabled: !!workspaceId && q.length > 0,
  });
}

export function useMemoryMutations() {
  const { workspaceId } = useWorkspace();
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["memories", workspaceId] });

  return {
    create: useMutation({
      mutationFn: (input: MemoryInput) => createMemory(workspaceId!, input),
      onSuccess: refresh,
    }),
    update: useMutation({
      mutationFn: ({ id, patch }: { id: string; patch: Partial<MemoryInput> }) =>
        updateMemory(workspaceId!, id, patch),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: string) => deleteMemory(workspaceId!, id),
      onSuccess: refresh,
    }),
  };
}
