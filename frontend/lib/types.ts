// Types mirroring the backend API schemas (backend/app/schemas).

export interface User {
  id: string;
  email: string;
  full_name: string;
  created_at: string;
}

export type WorkspaceRole = "owner" | "admin" | "member";

export interface Workspace {
  id: string;
  name: string;
  role: WorkspaceRole;
  created_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export const TASK_STATUSES = ["todo", "in_progress", "completed", "cancelled"] as const;
export type TaskStatus = (typeof TASK_STATUSES)[number];

export const TASK_PRIORITIES = ["low", "medium", "high", "urgent"] as const;
export type TaskPriority = (typeof TASK_PRIORITIES)[number];

export interface Task {
  id: string;
  workspace_id: string;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  due_date: string | null;
  source: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface Note {
  id: string;
  workspace_id: string;
  title: string;
  content: string;
  tags: string[];
  created_at: string;
  updated_at: string;
}

/** List-view note: a short preview instead of the full content. */
export interface NoteSummary {
  id: string;
  workspace_id: string;
  title: string;
  preview: string;
  tags: string[];
  created_at: string;
  updated_at: string;
}

// --- Documents ---------------------------------------------------------------

export type DocumentStatus = "pending" | "processing" | "ready" | "failed";

export interface DocumentItem {
  id: string;
  workspace_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: DocumentStatus;
  error: string | null;
  chunk_count: number;
  created_at: string;
  processed_at: string | null;
}

/** A passage from a document that matched a search. */
export interface DocumentSearchHit {
  document_id: string;
  filename: string;
  chunk_index: number;
  content: string;
  score: number;
}

// --- Memory ------------------------------------------------------------------

export const MEMORY_KINDS = [
  "person",
  "project",
  "preference",
  "commitment",
  "event",
  "decision",
  "fact",
] as const;
export type MemoryKind = (typeof MEMORY_KINDS)[number];
export type MemorySource = "conversation" | "note" | "document" | "manual";

export interface Memory {
  id: string;
  workspace_id: string;
  kind: MemoryKind;
  content: string;
  subject: string | null;
  source_type: MemorySource;
  source_id: string | null;
  source_label: string | null;
  confidence: number | null;
  extraction: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface MemorySearchHit {
  memory: Memory;
  score: number;
}

// --- Search ------------------------------------------------------------------

export const SEARCH_TYPES = ["task", "note", "document", "memory"] as const;
export type SearchType = (typeof SEARCH_TYPES)[number];

export interface SearchResult {
  type: SearchType;
  id: string;
  title: string;
  snippet: string;
  /** 0-1 relevance, or null when the results are a filter-only listing. */
  score: number | null;
  updated_at: string;
  tags: string[] | null;
  status: TaskStatus | null;
  priority: TaskPriority | null;
  due_date: string | null;
  kind: MemoryKind | null;
}

/** What the server understood from the query (filters typed into it, content types searched). */
export interface SearchApplied {
  text: string;
  types: SearchType[];
  tags: string[];
  status: TaskStatus | null;
  priority: TaskPriority | null;
  overdue: boolean | null;
  kind: MemoryKind | null;
}

export interface SearchResponse {
  applied: SearchApplied;
  results: SearchResult[];
}

// --- AI assistant -----------------------------------------------------------

/** One tool the assistant ran while answering: what it did and whether it worked. */
export interface ToolEvent {
  name: string;
  input: Record<string, unknown>;
  ok: boolean;
  result: Record<string, unknown> | null;
  error: string | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  tool_events: ToolEvent[];
  provider: string | null;
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: ChatMessage[];
}

export interface ChatResponse {
  conversation_id: string;
  message: ChatMessage;
  provider: string;
}

export interface AssistantStatus {
  provider: string;
  /** True when the built-in demo model is answering instead of a real AI model. */
  demo: boolean;
}
