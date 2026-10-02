"use client";

import { describeToolEvent } from "@/lib/assistant-events";
import type { ChatMessage } from "@/lib/types";

export function MessageBubble({ message }: { message: Pick<ChatMessage, "role" | "content" | "tool_events"> }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[85%] space-y-2 ${isUser ? "items-end" : ""}`}>
        <div
          className={`whitespace-pre-wrap break-words rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
            isUser
              ? "bg-accent text-accent-foreground"
              : "border border-border bg-surface"
          }`}
        >
          {message.content}
        </div>
        {message.tool_events.length > 0 && (
          <ul className="space-y-1" aria-label="Actions taken">
            {message.tool_events.map((event, i) => {
              const { label, ok } = describeToolEvent(event);
              return (
                <li
                  key={i}
                  className={`flex items-center gap-1.5 text-xs ${ok ? "text-muted-foreground" : "text-danger"}`}
                >
                  <span aria-hidden="true">{ok ? "✓" : "✕"}</span>
                  <span>{label}</span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

export function ThinkingBubble() {
  return (
    <div className="flex justify-start" role="status" aria-label="Assistant is thinking">
      <div className="flex gap-1 rounded-2xl border border-border bg-surface px-4 py-3">
        {[0, 150, 300].map((delay) => (
          <span
            key={delay}
            className="size-1.5 animate-bounce rounded-full bg-muted-foreground"
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
      </div>
    </div>
  );
}
