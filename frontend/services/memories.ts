import { api } from "@/lib/api-client";
import type { Memory, MemoryKind, MemorySearchHit, Page } from "@/lib/types";

export interface MemoryQuery {
  kind?: MemoryKind;
  limit?: number;
  offset?: number;
}

export interface MemoryInput {
  content: string;
  kind: MemoryKind;
  subject: string | null;
}

const base = (workspaceId: string) => `workspaces/${workspaceId}/memories`;

export const listMemories = (workspaceId: string, query: MemoryQuery = {}) =>
  api<Page<Memory>>(base(workspaceId), { query: { ...query } });

export const searchMemories = (workspaceId: string, q: string, kind?: MemoryKind) =>
  api<MemorySearchHit[]>(`${base(workspaceId)}/search`, { query: { q, kind, limit: 10 } });

export const createMemory = (workspaceId: string, input: MemoryInput) =>
  api<Memory>(base(workspaceId), { method: "POST", body: input });

export const updateMemory = (workspaceId: string, memoryId: string, patch: Partial<MemoryInput>) =>
  api<Memory>(`${base(workspaceId)}/${memoryId}`, { method: "PATCH", body: patch });

export const deleteMemory = (workspaceId: string, memoryId: string) =>
  api<void>(`${base(workspaceId)}/${memoryId}`, { method: "DELETE" });
