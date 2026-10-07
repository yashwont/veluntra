import { api, apiUpload } from "@/lib/api-client";
import type { DocumentItem, DocumentSearchHit, DocumentStatus, Page } from "@/lib/types";

export interface DocumentQuery {
  status?: DocumentStatus;
  limit?: number;
  offset?: number;
}

const base = (workspaceId: string) => `workspaces/${workspaceId}/documents`;

/** Same-origin URL that downloads the original file (the browser sends its session cookie). */
export const documentDownloadUrl = (workspaceId: string, documentId: string) =>
  `/api/backend/${base(workspaceId)}/${documentId}/download`;

export const listDocuments = (workspaceId: string, query: DocumentQuery = {}) =>
  api<Page<DocumentItem>>(base(workspaceId), { query: { ...query } });

export const uploadDocument = (workspaceId: string, file: File) =>
  apiUpload<DocumentItem>(base(workspaceId), file);

export const reprocessDocument = (workspaceId: string, documentId: string) =>
  api<DocumentItem>(`${base(workspaceId)}/${documentId}/reprocess`, { method: "POST" });

export const deleteDocument = (workspaceId: string, documentId: string) =>
  api<void>(`${base(workspaceId)}/${documentId}`, { method: "DELETE" });

export const searchDocuments = (workspaceId: string, q: string, limit = 5) =>
  api<DocumentSearchHit[]>(`${base(workspaceId)}/search`, { query: { q, limit } });
