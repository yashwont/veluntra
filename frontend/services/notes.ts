import { api } from "@/lib/api-client";
import type { Note, NoteSummary, Page } from "@/lib/types";

export interface NoteQuery {
  q?: string;
  tag?: string[];
  limit?: number;
  offset?: number;
}

export interface NoteInput {
  title: string;
  content?: string;
  tags?: string[];
}

const base = (workspaceId: string) => `workspaces/${workspaceId}/notes`;

export const listNotes = (workspaceId: string, query: NoteQuery = {}) =>
  api<Page<NoteSummary>>(base(workspaceId), { query: { ...query } });

export const getNote = (workspaceId: string, noteId: string) =>
  api<Note>(`${base(workspaceId)}/${noteId}`);

export const createNote = (workspaceId: string, input: NoteInput) =>
  api<Note>(base(workspaceId), { method: "POST", body: input });

export const updateNote = (workspaceId: string, noteId: string, patch: Partial<NoteInput>) =>
  api<Note>(`${base(workspaceId)}/${noteId}`, { method: "PATCH", body: patch });

export const deleteNote = (workspaceId: string, noteId: string) =>
  api<void>(`${base(workspaceId)}/${noteId}`, { method: "DELETE" });
