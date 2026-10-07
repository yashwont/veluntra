"use client";

import { useEffect, useRef, useState } from "react";

import { MessageBubble, ThinkingBubble } from "@/components/assistant/message-bubble";
import { Button, ErrorBanner, Select, Spinner } from "@/components/ui";
import { useAssistantStatus, useChat, useConversations } from "@/hooks/use-chat";

const EXAMPLES = [
  "Create a high priority task to finish my proposal tomorrow",
  "What are my overdue tasks?",
  "Remind me to call Ram next Monday",
  "Search notes for proposal",
];

const MAX_LENGTH = 4000;

export default function AssistantPage() {
  const chat = useChat();
  const status = useAssistantStatus();
  const conversations = useConversations();
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const busy = chat.send.isPending;
  const hasMessages = chat.messages.length > 0 || chat.pendingMessage !== null;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [chat.messages.length, chat.pendingMessage, busy]);

  function submit(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    chat.send.mutate(message, { onSuccess: () => setDraft("") });
  }

  return (
    <div className="flex h-[calc(100dvh-8.5rem)] min-h-[28rem] flex-col md:h-[calc(100dvh-4rem)]">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Assistant</h1>
        <div className="flex items-center gap-2">
          <Select
            aria-label="Conversation"
            value={chat.conversationId ?? ""}
            onChange={(e) => chat.open(e.target.value || null)}
            className="max-w-[16rem]"
          >
            <option value="">New chat</option>
            {conversations.data?.items.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title}
              </option>
            ))}
          </Select>
          {chat.conversationId && (
            <Button
              variant="danger"
              disabled={chat.remove.isPending}
              onClick={() => {
                if (confirm("Delete this conversation? This can't be undone.")) {
                  chat.remove.mutate(chat.conversationId!);
                }
              }}
            >
              Delete
            </Button>
          )}
        </div>
      </div>

      {status.data?.demo && (
        <p role="note" className="mb-3 rounded-lg bg-accent-soft px-3.5 py-2.5 text-sm text-accent">
          Demo mode: no AI model is connected yet, so I only understand a few phrasings. Everything
          else (creating tasks and notes, searching) works for real.
        </p>
      )}

      {status.data && !status.data.demo && (
        <p className="mb-3 text-xs text-muted-foreground">
          Answering with {status.data.model ?? status.data.provider}
          {status.data.provider === "ollama" ? ", running on this computer" : ""}.
        </p>
      )}

      <div
        className="min-h-0 flex-1 space-y-3 overflow-y-auto rounded-xl border border-border bg-background p-4"
        aria-live="polite"
        aria-label="Conversation"
      >
        {chat.isLoadingConversation ? (
          <Spinner />
        ) : !hasMessages ? (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <div>
              <p className="font-medium">What can I help with?</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Ask me to create tasks and notes, or to find them.
              </p>
            </div>
            <div className="flex max-w-xl flex-wrap justify-center gap-2">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  type="button"
                  disabled={busy}
                  onClick={() => submit(example)}
                  className="rounded-full border border-border bg-surface px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {chat.messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}
            {chat.pendingMessage !== null && (
              <MessageBubble message={{ role: "user", content: chat.pendingMessage, tool_events: [] }} />
            )}
            {busy && <ThinkingBubble />}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="mt-3 space-y-2">
        <ErrorBanner error={chat.send.error ?? chat.loadError ?? chat.remove.error} />
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit(draft);
          }}
          className="flex items-end gap-2"
        >
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              // Enter sends; Shift+Enter inserts a newline
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                submit(draft);
              }
            }}
            rows={2}
            maxLength={MAX_LENGTH}
            placeholder={"Ask Veluntra anything…"}
            aria-label="Message"
            disabled={busy}
            className="w-full resize-none rounded-xl border border-border bg-surface px-3.5 py-2.5 text-sm placeholder:text-muted-foreground focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25 disabled:opacity-60"
          />
          <Button type="submit" disabled={busy || !draft.trim()} className="h-[2.75rem] shrink-0">
            Send
          </Button>
        </form>
      </div>
    </div>
  );
}
