"use client";

import { useState } from "react";

import { Button, ErrorBanner, Field, Input, Select, Textarea } from "@/components/ui";
import { useMemoryMutations } from "@/hooks/use-memories";
import { ApiError } from "@/lib/api-client";
import { KIND_LABELS } from "@/lib/memory-meta";
import { MEMORY_KINDS, type Memory, type MemoryKind } from "@/lib/types";

/** Add (no `memory`) or edit (`memory`) form. Rendered inside a Modal. */
export function MemoryForm({ memory, onDone }: { memory?: Memory; onDone: () => void }) {
  const { create, update } = useMemoryMutations();
  const [content, setContent] = useState(memory?.content ?? "");
  const [kind, setKind] = useState<MemoryKind>(memory?.kind ?? "fact");
  const [subject, setSubject] = useState(memory?.subject ?? "");

  const mutation = memory ? update : create;
  const error = mutation.error instanceof ApiError ? mutation.error : null;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const fields = { content, kind, subject: subject.trim() || null };
    if (memory) update.mutate({ id: memory.id, patch: fields }, { onSuccess: onDone });
    else create.mutate(fields, { onSuccess: onDone });
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <Field label="What should be remembered?" htmlFor="memory-content" error={error?.fieldError("content")}>
        <Textarea
          id="memory-content"
          rows={4}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          maxLength={1000}
          required
          autoFocus
          placeholder="e.g. Ram prefers email over phone calls"
        />
      </Field>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Kind" htmlFor="memory-kind">
          <Select id="memory-kind" className="w-full" value={kind} onChange={(e) => setKind(e.target.value as MemoryKind)}>
            {MEMORY_KINDS.map((k) => (
              <option key={k} value={k}>
                {KIND_LABELS[k]}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="About (optional)" htmlFor="memory-subject" error={error?.fieldError("subject")}>
          <Input
            id="memory-subject"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            maxLength={200}
            placeholder="A person or project"
          />
        </Field>
      </div>

      {/* A duplicate is a 409 with a plain-language message, not a field error */}
      {error && !error.fieldError("content") && !error.fieldError("subject") && <ErrorBanner error={error} />}

      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={mutation.isPending || !content.trim()}>
          {mutation.isPending ? "Saving…" : memory ? "Save" : "Remember"}
        </Button>
      </div>
    </form>
  );
}
