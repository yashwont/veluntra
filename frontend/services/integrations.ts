import { api } from "@/lib/api-client";
import type {
  CalendarResponse,
  DocumentItem,
  DriveFile,
  EmailSummary,
  IntegrationsResponse,
} from "@/lib/types";

const base = (workspaceId: string) => `workspaces/${workspaceId}/integrations`;

export const listIntegrations = (workspaceId: string) =>
  api<IntegrationsResponse>(base(workspaceId));

/** Returns the Google consent URL: send the browser there. */
export const startGoogleConnect = (workspaceId: string) =>
  api<{ authorization_url: string }>(`${base(workspaceId)}/google/connect`, { method: "POST" });

export const disconnectIntegration = (workspaceId: string, accountId: string) =>
  api<void>(`${base(workspaceId)}/${accountId}`, { method: "DELETE" });

export const getCalendar = (workspaceId: string, days: number) =>
  api<CalendarResponse>(`${base(workspaceId)}/google/calendar/events`, {
    query: { days, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC" },
  });

export const searchEmail = (workspaceId: string, q: string) =>
  api<EmailSummary[]>(`${base(workspaceId)}/google/gmail/messages`, { query: { q, limit: 10 } });

export const searchDrive = (workspaceId: string, q: string) =>
  api<DriveFile[]>(`${base(workspaceId)}/google/drive/files`, { query: { q, limit: 10 } });

export const importDriveFile = (workspaceId: string, fileId: string) =>
  api<DocumentItem>(`${base(workspaceId)}/google/drive/files/${fileId}/import`, { method: "POST" });
