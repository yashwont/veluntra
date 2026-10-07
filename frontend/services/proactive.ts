import { api } from "@/lib/api-client";
import type { Briefing, Suggestion, Task } from "@/lib/types";

const base = (workspaceId: string) => `workspaces/${workspaceId}`;
const timezone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

export const getBriefing = (workspaceId: string) =>
  api<Briefing>(`${base(workspaceId)}/briefing`, { query: { timezone: timezone() } });

export const listSuggestions = (workspaceId: string) =>
  api<Suggestion[]>(`${base(workspaceId)}/suggestions`);

export const scanForSuggestions = (workspaceId: string) =>
  api<{ created: number; pending: Suggestion[] }>(`${base(workspaceId)}/suggestions/scan`, {
    method: "POST",
    query: { timezone: timezone() },
  });

export const acceptSuggestion = (workspaceId: string, id: string) =>
  api<{ suggestion: Suggestion; task: Task }>(`${base(workspaceId)}/suggestions/${id}/accept`, {
    method: "POST",
  });

export const dismissSuggestion = (workspaceId: string, id: string) =>
  api<Suggestion>(`${base(workspaceId)}/suggestions/${id}/dismiss`, { method: "POST" });
