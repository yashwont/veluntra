"use client";

import { useState } from "react";

import { MemoryForm } from "@/components/memory/memory-form";
import { Badge, Button, EmptyState, ErrorBanner, Input, Modal, Spinner } from "@/components/ui";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useMemories, useMemoryMutations, useMemorySearch } from "@/hooks/use-memories";
import { useNow } from "@/hooks/use-now";
import { timeAgo } from "@/lib/dates";
import { KIND_LABELS, describeSource } from "@/lib/memory-meta";
import { MEMORY_KINDS, type Memory, type MemoryKind } from "@/lib/types";

const PAGE_SIZE = 20;

function MemoryCard({
  memory,
  now,
  score,
  onEdit,
}: {
  memory: Memory;
  now: number;
  score?: number;
  onEdit: (memory: Memory) => void;
}) {
  const { remove } = useMemoryMutations();
  const [confirming, setConfirming] = useState(false);

  return (
    <li className="px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-1.5">
            <Badge tone="accent">{KIND_LABELS[memory.kind]}</Badge>
            {memory.subject && <span className="text-sm font-medium">{memory.subject}</span>}
            {score !== undefined && (
              <span className="text-xs text-muted-foreground">match {Math.round(score * 100)}%</span>
            )}
          </p>
          <p className="mt-1.5 whitespace-pre-line break-words text-sm">{memory.content}</p>
          <p className="mt-1.5 text-xs text-muted-foreground">
            {describeSource(memory)} · {timeAgo(memory.updated_at, now)}
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-1">
          {confirming ? (
            <>
              <Button
                variant="danger"
                disabled={remove.isPending}
                onClick={() => remove.mutate(memory.id, { onSettled: () => setConfirming(false) })}
              >
                Forget
              </Button>
              <Button variant="ghost" onClick={() => setConfirming(false)}>
                Cancel
              </Button>
            </>
          ) : (
            <>
              <Button variant="ghost" onClick={() => onEdit(memory)}>
                Edit
              </Button>
              <Button variant="ghost" onClick={() => setConfirming(true)}>
                Forget
              </Button>
            </>
          )}
        </div>
      </div>
      {remove.error && (
        <div className="mt-2">
          <ErrorBanner error={remove.error} />
        </div>
      )}
    </li>
  );
}

export default function MemoryPage() {
  const now = useNow();
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState<MemoryKind | null>(null);
  const [offset, setOffset] = useState(0);
  // undefined = closed, null = adding a new one, a Memory = editing it
  const [editing, setEditing] = useState<Memory | null | undefined>(undefined);

  const q = useDebouncedValue(search.trim(), 400);
  const memories = useMemories({ kind: kind ?? undefined, limit: PAGE_SIZE, offset });
  const results = useMemorySearch(q, kind ?? undefined);

  const items = memories.data?.items ?? [];
  const total = memories.data?.total ?? 0;
  const searching = q.length > 0;
  const shown = searching ? results : memories;

  return (
    <>
      <div className="mb-2 flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">Memory</h1>
        <Button onClick={() => setEditing(null)}>Add memory</Button>
      </div>
      <p className="mb-6 max-w-2xl text-sm text-muted-foreground">
        Lasting facts the assistant can recall: people, projects, preferences, commitments and decisions. It saves one
        only when something is worth remembering, always tells you, and you can edit or forget anything here.
      </p>

      <Input
        type="search"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search your memories…"
        aria-label="Search memories"
        maxLength={500}
      />

      <div className="mt-3 flex flex-wrap gap-1.5" role="group" aria-label="Filter by kind">
        {MEMORY_KINDS.map((k) => (
          <button
            key={k}
            type="button"
            aria-pressed={kind === k}
            onClick={() => {
              setKind(kind === k ? null : k);
              setOffset(0);
            }}
            className={`rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
              kind === k ? "bg-accent text-accent-foreground" : "bg-muted text-muted-foreground hover:text-foreground"
            }`}
          >
            {KIND_LABELS[k]}
          </button>
        ))}
      </div>

      <div className="mt-4">
        {shown.isLoading ? (
          <Spinner />
        ) : shown.error ? (
          <ErrorBanner error={shown.error} />
        ) : searching ? (
          (results.data ?? []).length === 0 ? (
            <EmptyState title="Nothing matches" description="Try different words, or clear the kind filter." />
          ) : (
            <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
              {(results.data ?? []).map((hit) => (
                <MemoryCard key={hit.memory.id} memory={hit.memory} score={hit.score} now={now} onEdit={setEditing} />
              ))}
            </ul>
          )
        ) : items.length === 0 ? (
          <EmptyState
            title={kind ? "No memories of this kind" : "Nothing remembered yet"}
            description='Add one yourself, or tell the assistant: "Remember that Ram prefers email over calls".'
          />
        ) : (
          <>
            <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
              {items.map((memory) => (
                <MemoryCard key={memory.id} memory={memory} now={now} onEdit={setEditing} />
              ))}
            </ul>

            {total > PAGE_SIZE && (
              <div className="mt-3 flex items-center justify-between text-sm text-muted-foreground">
                <span>
                  {offset + 1}–{offset + items.length} of {total}
                </span>
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                  >
                    Prev
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={offset + PAGE_SIZE >= total}
                    onClick={() => setOffset(offset + PAGE_SIZE)}
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      <Modal
        open={editing !== undefined}
        onClose={() => setEditing(undefined)}
        title={editing ? "Edit memory" : "Add memory"}
      >
        <MemoryForm memory={editing ?? undefined} onDone={() => setEditing(undefined)} />
      </Modal>
    </>
  );
}
