"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { useWorkspace } from "@/hooks/use-workspace";
import type { SearchType } from "@/lib/types";
import { searchEverything } from "@/services/search";

export function useSearch(q: string, types: SearchType[]) {
  const { workspaceId } = useWorkspace();
  return useQuery({
    queryKey: ["search", workspaceId, q, types],
    queryFn: () => searchEverything(workspaceId!, q, types),
    enabled: !!workspaceId && q.length > 0,
    placeholderData: keepPreviousData,
  });
}
