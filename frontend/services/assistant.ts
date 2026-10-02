import { api } from "@/lib/api-client";
import type {
  AssistantStatus,
  ChatResponse,
  Conversation,
  ConversationDetail,
  Page,
} from "@/lib/types";

const base = (workspaceId: string) => `workspaces/${workspaceId}`;

export const getAssistantStatus = (workspaceId: string) =>
  api<AssistantStatus>(`${base(workspaceId)}/assistant/status`);

export const sendMessage = (
  workspaceId: string,
  input: { message: string; conversation_id: string | null; timezone: string },
) => api<ChatResponse>(`${base(workspaceId)}/assistant/chat`, { method: "POST", body: input });

export const listConversations = (workspaceId: string) =>
  api<Page<Conversation>>(`${base(workspaceId)}/conversations`, { query: { limit: 50 } });

export const getConversation = (workspaceId: string, conversationId: string) =>
  api<ConversationDetail>(`${base(workspaceId)}/conversations/${conversationId}`);

export const deleteConversation = (workspaceId: string, conversationId: string) =>
  api<void>(`${base(workspaceId)}/conversations/${conversationId}`, { method: "DELETE" });
