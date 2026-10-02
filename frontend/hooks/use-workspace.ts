"use client";

import { useQuery } from "@tanstack/react-query";

import { listWorkspaces } from "@/services/workspaces";

/**
 * The workspace the UI is operating in. Every user currently has exactly one
 * (their personal workspace), so this is the first one. A workspace switcher
 * would change only this hook.
 */
export function useWorkspace() {
  const query = useQuery({
    queryKey: ["workspaces"],
    queryFn: listWorkspaces,
    staleTime: 5 * 60_000,
  });
  const workspace = query.data?.[0];
  return {
    workspaceId: workspace?.id,
    workspace,
    isLoading: query.isLoading,
    error: query.error,
  };
}
