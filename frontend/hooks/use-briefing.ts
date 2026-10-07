"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useWorkspace } from "@/hooks/use-workspace";
import {
  acceptSuggestion,
  dismissSuggestion,
  getBriefing,
  listSuggestions,
  scanForSuggestions,
} from "@/services/proactive";

export function useBriefing() {
  const { workspaceId } = useWorkspace();
  return useQuery({
    queryKey: ["briefing", workspaceId],
    queryFn: () => getBriefing(workspaceId!),
    enabled: !!workspaceId,
    staleTime: 60_000,
  });
}

export function useSuggestions() {
  const { workspaceId } = useWorkspace();
  return useQuery({
    queryKey: ["suggestions", workspaceId],
    queryFn: () => listSuggestions(workspaceId!),
    enabled: !!workspaceId,
  });
}

export function useSuggestionMutations() {
  const { workspaceId } = useWorkspace();
  const queryClient = useQueryClient();
  const refresh = (...keys: string[]) =>
    Promise.all(keys.map((key) => queryClient.invalidateQueries({ queryKey: [key, workspaceId] })));

  return {
    scan: useMutation({
      mutationFn: () => scanForSuggestions(workspaceId!),
      onSuccess: () => refresh("suggestions", "briefing"),
    }),
    // Accepting creates a real task, so the task lists change too
    accept: useMutation({
      mutationFn: (id: string) => acceptSuggestion(workspaceId!, id),
      onSuccess: () => refresh("suggestions", "briefing", "tasks"),
    }),
    dismiss: useMutation({
      mutationFn: (id: string) => dismissSuggestion(workspaceId!, id),
      onSuccess: () => refresh("suggestions", "briefing"),
    }),
  };
}
