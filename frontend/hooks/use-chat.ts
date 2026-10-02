"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useWorkspace } from "@/hooks/use-workspace";
import { NOTE_WRITE_TOOLS, TASK_WRITE_TOOLS } from "@/lib/assistant-events";
import type { ChatMessage, ConversationDetail } from "@/lib/types";
import {
  deleteConversation,
  getAssistantStatus,
  getConversation,
  listConversations,
  sendMessage,
} from "@/services/assistant";

export function useAssistantStatus() {
  const { workspaceId } = useWorkspace();
  return useQuery({
    queryKey: ["assistant-status", workspaceId],
    queryFn: () => getAssistantStatus(workspaceId!),
    enabled: !!workspaceId,
    staleTime: 5 * 60_000,
  });
}

export function useConversations() {
  const { workspaceId } = useWorkspace();
  return useQuery({
    queryKey: ["conversations", workspaceId],
    queryFn: () => listConversations(workspaceId!),
    enabled: !!workspaceId,
  });
}

/** State and actions for one chat view: which conversation is open, and sending. */
export function useChat() {
  const { workspaceId } = useWorkspace();
  const queryClient = useQueryClient();
  const [conversationId, setConversationId] = useState<string | null>(null);

  const detailKey = (id: string | null) => ["conversation", workspaceId, id];

  const detail = useQuery({
    queryKey: detailKey(conversationId),
    queryFn: () => getConversation(workspaceId!, conversationId!),
    enabled: !!workspaceId && !!conversationId,
  });

  const send = useMutation({
    mutationFn: (message: string) =>
      sendMessage(workspaceId!, {
        message,
        conversation_id: conversationId,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
      }),
    onSuccess: (response, message) => {
      const now = new Date().toISOString();
      const userMessage: ChatMessage = {
        id: `local-${now}`,
        role: "user",
        content: message,
        tool_events: [],
        provider: null,
        created_at: now,
      };
      // Show both messages immediately; a background refetch later swaps in server copies
      queryClient.setQueryData<ConversationDetail>(detailKey(response.conversation_id), (old) => ({
        id: response.conversation_id,
        title: old?.title ?? message.slice(0, 60),
        created_at: old?.created_at ?? now,
        updated_at: now,
        messages: [...(old?.messages ?? []), userMessage, response.message],
      }));
      setConversationId(response.conversation_id);

      const ran = response.message.tool_events.filter((e) => e.ok).map((e) => e.name);
      if (ran.some((n) => TASK_WRITE_TOOLS.has(n))) {
        queryClient.invalidateQueries({ queryKey: ["tasks", workspaceId] });
      }
      if (ran.some((n) => NOTE_WRITE_TOOLS.has(n))) {
        queryClient.invalidateQueries({ queryKey: ["notes", workspaceId] });
      }
    },
    // The server saves the user's message even when the model fails, so the list changes either way
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["conversations", workspaceId] }),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteConversation(workspaceId!, id),
    onSuccess: (_data, id) => {
      queryClient.removeQueries({ queryKey: detailKey(id) });
      queryClient.invalidateQueries({ queryKey: ["conversations", workspaceId] });
      setConversationId(null);
    },
  });

  return {
    conversationId,
    open: (id: string | null) => {
      setConversationId(id);
      send.reset();
    },
    messages: detail.data?.messages ?? [],
    isLoadingConversation: !!conversationId && detail.isLoading,
    loadError: detail.error,
    send,
    // The message being sent, shown right away while we wait for the reply
    pendingMessage: send.isPending ? send.variables : null,
    remove,
  };
}
