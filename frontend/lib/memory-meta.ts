import type { Memory, MemoryKind } from "@/lib/types";

export const KIND_LABELS: Record<MemoryKind, string> = {
  person: "Person",
  project: "Project",
  preference: "Preference",
  commitment: "Commitment",
  event: "Event",
  decision: "Decision",
  fact: "Fact",
};

/** Where a memory came from, in plain words: shown so users can judge how far to trust it. */
export function describeSource(memory: Pick<Memory, "source_type" | "source_label" | "confidence">): string {
  const confidence = memory.confidence === null ? "" : ` · ${Math.round(memory.confidence * 100)}% sure`;
  switch (memory.source_type) {
    case "manual":
      return "Added by you";
    case "conversation":
      return `From a chat${memory.source_label ? `: “${memory.source_label}”` : ""}${confidence}`;
    case "note":
      return `From a note${memory.source_label ? `: “${memory.source_label}”` : ""}${confidence}`;
    case "document":
      return `From a document${memory.source_label ? `: ${memory.source_label}` : ""}${confidence}`;
  }
}
