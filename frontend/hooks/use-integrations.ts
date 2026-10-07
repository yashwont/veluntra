"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useWorkspace } from "@/hooks/use-workspace";
import {
  disconnectIntegration,
  getCalendar,
  importDriveFile,
  listIntegrations,
  searchDrive,
  searchEmail,
  startGoogleConnect,
} from "@/services/integrations";

export function useIntegrations() {
  const { workspaceId } = useWorkspace();
  return useQuery({
    queryKey: ["integrations", workspaceId],
    queryFn: () => listIntegrations(workspaceId!),
    enabled: !!workspaceId,
  });
}

export function useIntegrationMutations() {
  const { workspaceId } = useWorkspace();
  const queryClient = useQueryClient();
  return {
    // The browser leaves for Google, so there is nothing to refresh on success
    connect: useMutation({
      mutationFn: () => startGoogleConnect(workspaceId!),
      onSuccess: ({ authorization_url }) => window.location.assign(authorization_url),
    }),
    disconnect: useMutation({
      mutationFn: (accountId: string) => disconnectIntegration(workspaceId!, accountId),
      onSuccess: () => queryClient.invalidateQueries({ queryKey: ["integrations", workspaceId] }),
    }),
    importFile: useMutation({
      mutationFn: (fileId: string) => importDriveFile(workspaceId!, fileId),
      onSuccess: () => queryClient.invalidateQueries({ queryKey: ["documents", workspaceId] }),
    }),
  };
}

const MINUTE = 60_000;

export function useCalendar(enabled: boolean) {
  const { workspaceId } = useWorkspace();
  return useQuery({
    queryKey: ["google", workspaceId, "calendar"],
    queryFn: () => getCalendar(workspaceId!, 7),
    enabled: enabled && !!workspaceId,
    staleTime: 2 * MINUTE,
    retry: false,
  });
}

export function useEmailSearch(q: string, enabled: boolean) {
  const { workspaceId } = useWorkspace();
  return useQuery({
    queryKey: ["google", workspaceId, "gmail", q],
    queryFn: () => searchEmail(workspaceId!, q),
    enabled: enabled && !!workspaceId,
    staleTime: MINUTE,
    retry: false,
  });
}

export function useDriveSearch(q: string, enabled: boolean) {
  const { workspaceId } = useWorkspace();
  return useQuery({
    queryKey: ["google", workspaceId, "drive", q],
    queryFn: () => searchDrive(workspaceId!, q),
    enabled: enabled && !!workspaceId,
    staleTime: MINUTE,
    retry: false,
  });
}
