"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useWorkspace } from "@/hooks/use-workspace";
import {
  type DocumentQuery,
  deleteDocument,
  listDocuments,
  reprocessDocument,
  searchDocuments,
  uploadDocument,
} from "@/services/documents";

/** How often to re-check while some document is still being processed. */
const POLL_MS = 2000;

export function useDocuments(query: DocumentQuery) {
  const { workspaceId } = useWorkspace();
  return useQuery({
    queryKey: ["documents", workspaceId, "list", query],
    queryFn: () => listDocuments(workspaceId!, query),
    enabled: !!workspaceId,
    placeholderData: keepPreviousData,
    // Processing happens in the background: keep polling until nothing is in flight
    refetchInterval: (q) =>
      q.state.data?.items.some((d) => d.status === "pending" || d.status === "processing")
        ? POLL_MS
        : false,
  });
}

export function useDocumentSearch(q: string) {
  const { workspaceId } = useWorkspace();
  return useQuery({
    queryKey: ["documents", workspaceId, "search", q],
    queryFn: () => searchDocuments(workspaceId!, q),
    enabled: !!workspaceId && q.length > 0,
  });
}

export function useDocumentMutations() {
  const { workspaceId } = useWorkspace();
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["documents", workspaceId] });

  return {
    upload: useMutation({
      mutationFn: (file: File) => uploadDocument(workspaceId!, file),
      onSuccess: refresh,
    }),
    reprocess: useMutation({
      mutationFn: (id: string) => reprocessDocument(workspaceId!, id),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: string) => deleteDocument(workspaceId!, id),
      onSuccess: refresh,
    }),
  };
}
