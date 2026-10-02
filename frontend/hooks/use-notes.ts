"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useWorkspace } from "@/hooks/use-workspace";
import {
  type NoteInput,
  type NoteQuery,
  createNote,
  deleteNote,
  getNote,
  listNotes,
  updateNote,
} from "@/services/notes";

export function useNotes(query: NoteQuery) {
  const { workspaceId } = useWorkspace();
  return useQuery({
    queryKey: ["notes", workspaceId, "list", query],
    queryFn: () => listNotes(workspaceId!, query),
    enabled: !!workspaceId,
    placeholderData: keepPreviousData,
  });
}

export function useNote(noteId: string | null) {
  const { workspaceId } = useWorkspace();
  return useQuery({
    queryKey: ["notes", workspaceId, "detail", noteId],
    queryFn: () => getNote(workspaceId!, noteId!),
    enabled: !!workspaceId && !!noteId,
  });
}

export function useNoteMutations() {
  const { workspaceId } = useWorkspace();
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["notes", workspaceId] });

  return {
    create: useMutation({
      mutationFn: (input: NoteInput) => createNote(workspaceId!, input),
      onSuccess: refresh,
    }),
    update: useMutation({
      mutationFn: ({ id, patch }: { id: string; patch: Partial<NoteInput> }) =>
        updateNote(workspaceId!, id, patch),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: string) => deleteNote(workspaceId!, id),
      onSuccess: refresh,
    }),
  };
}
