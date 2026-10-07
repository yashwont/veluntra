import { api } from "@/lib/api-client";
import type { SearchResponse, SearchType } from "@/lib/types";

export const searchEverything = (workspaceId: string, q: string, types: SearchType[] = []) =>
  api<SearchResponse>(`workspaces/${workspaceId}/search`, { query: { q, types, limit: 30 } });
