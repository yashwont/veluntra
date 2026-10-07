import type { ToolEvent } from "@/lib/types";

const text = (value: unknown): string => (typeof value === "string" ? value : "");

/** A one-line, human-readable description of what the assistant did with a tool. */
export function describeToolEvent(event: ToolEvent): { label: string; ok: boolean } {
  if (!event.ok) {
    return { ok: false, label: `Couldn't ${event.name.replace("_", " ")}: ${event.error ?? "failed"}` };
  }
  const result = event.result ?? {};
  switch (event.name) {
    case "create_task":
      return { ok: true, label: `Created task “${text((result.task as { title?: string })?.title)}”` };
    case "create_note":
      return { ok: true, label: `Saved note “${text((result.note as { title?: string })?.title)}”` };
    case "search_tasks":
      return { ok: true, label: `Looked up tasks · ${result.total ?? 0} found` };
    case "search_notes":
      return { ok: true, label: `Searched notes · ${result.total ?? 0} found` };
    case "search_documents":
      return { ok: true, label: `Searched documents · ${(result.passages as unknown[] | undefined)?.length ?? 0} passages` };
    case "remember":
      return {
        ok: true,
        label: result.already_known
          ? "Already remembered"
          : `Remembered: “${text((result.memory as { content?: string })?.content)}”`,
      };
    case "search_memories":
      return { ok: true, label: `Recalled memories · ${(result.memories as unknown[] | undefined)?.length ?? 0} found` };
    default:
      return { ok: true, label: event.name.replace("_", " ") };
  }
}

/** Tools that change the user's data, so the tasks/notes screens must refetch. */
export const TASK_WRITE_TOOLS = new Set(["create_task"]);
export const NOTE_WRITE_TOOLS = new Set(["create_note"]);
export const MEMORY_WRITE_TOOLS = new Set(["remember"]);
