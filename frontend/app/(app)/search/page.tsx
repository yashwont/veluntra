"use client";

import Link from "next/link";
import { useState } from "react";

import { Badge, EmptyState, ErrorBanner, Input, Spinner } from "@/components/ui";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useNow } from "@/hooks/use-now";
import { useSearch } from "@/hooks/use-search";
import { formatDue, timeAgo } from "@/lib/dates";
import { KIND_LABELS } from "@/lib/memory-meta";
import { PRIORITY_LABELS, PRIORITY_TONES, STATUS_LABELS } from "@/lib/task-meta";
import { SEARCH_TYPES, type SearchApplied, type SearchResult, type SearchType } from "@/lib/types";

const TYPE_LABELS: Record<SearchType, string> = {
  task: "Tasks",
  note: "Notes",
  document: "Documents",
  memory: "Memories",
};
const TYPE_SINGULAR: Record<SearchType, string> = {
  task: "Task",
  note: "Note",
  document: "Document",
  memory: "Memory",
};
const TYPE_HREF: Record<SearchType, string> = {
  task: "/tasks",
  note: "/notes",
  document: "/documents",
  memory: "/memory",
};

const EXAMPLES = ["proposal priority:high", "is:overdue", "ideas tag:work", "kind:person Ram", "type:documents budget"];

function Meta({ result, now }: { result: SearchResult; now: number }) {
  return (
    <span className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
      {result.type === "task" && result.priority && (
        <Badge tone={PRIORITY_TONES[result.priority]}>{PRIORITY_LABELS[result.priority]}</Badge>
      )}
      {result.type === "task" && result.status && <span>{STATUS_LABELS[result.status]}</span>}
      {result.type === "task" && result.due_date && <span>due {formatDue(result.due_date)}</span>}
      {result.type === "note" && result.tags?.slice(0, 3).map((t) => <Badge key={t}>#{t}</Badge>)}
      {result.type === "memory" && result.kind && <Badge tone="accent">{KIND_LABELS[result.kind]}</Badge>}
      <span>{timeAgo(result.updated_at, now)}</span>
    </span>
  );
}

function AppliedSummary({ applied }: { applied: SearchApplied }) {
  const chips = [
    applied.priority && `priority: ${PRIORITY_LABELS[applied.priority]}`,
    applied.status && `status: ${STATUS_LABELS[applied.status]}`,
    applied.overdue && "overdue",
    ...applied.tags.map((t) => `tag: ${t}`),
    applied.kind && `kind: ${KIND_LABELS[applied.kind]}`,
  ].filter((c): c is string => !!c);
  if (chips.length === 0) return null;
  return (
    <p className="mt-3 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
      Filtering by
      {chips.map((c) => (
        <Badge key={c} tone="accent">
          {c}
        </Badge>
      ))}
      <span>
        · searching {applied.types.length > 0 ? applied.types.map((t) => TYPE_LABELS[t].toLowerCase()).join(", ") : "nothing"}
      </span>
    </p>
  );
}

export default function SearchPage() {
  const now = useNow();
  const [input, setInput] = useState("");
  const [types, setTypes] = useState<SearchType[]>([]);

  const q = useDebouncedValue(input.trim(), 350);
  const search = useSearch(q, types);
  const results = search.data?.results ?? [];

  const toggleType = (type: SearchType) =>
    setTypes((current) => (current.includes(type) ? current.filter((t) => t !== type) : [...current, type]));

  return (
    <>
      <h1 className="mb-6 text-2xl font-semibold tracking-tight">Search</h1>

      <Input
        type="search"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder="Search tasks, notes, documents and memories…"
        aria-label="Search everything"
        maxLength={500}
        autoFocus
      />

      <div className="mt-3 flex flex-wrap gap-1.5" role="group" aria-label="Limit to">
        {SEARCH_TYPES.map((type) => (
          <button
            key={type}
            type="button"
            aria-pressed={types.includes(type)}
            onClick={() => toggleType(type)}
            className={`rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
              types.includes(type)
                ? "bg-accent text-accent-foreground"
                : "bg-muted text-muted-foreground hover:text-foreground"
            }`}
          >
            {TYPE_LABELS[type]}
          </button>
        ))}
      </div>

      {search.data && <AppliedSummary applied={search.data.applied} />}

      <div className="mt-5">
        {!q ? (
          <div className="rounded-xl border border-dashed border-border px-5 py-8 text-center">
            <p className="font-medium">Search everything at once</p>
            <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
              Words find matching tasks and notes; documents and memories are matched by meaning. Add filters right in the
              box:
            </p>
            <p className="mt-3 flex flex-wrap justify-center gap-2">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => setInput(example)}
                  className="rounded-lg bg-muted px-2.5 py-1 font-mono text-xs text-muted-foreground hover:text-foreground"
                >
                  {example}
                </button>
              ))}
            </p>
          </div>
        ) : search.isLoading ? (
          <Spinner label="Searching" />
        ) : search.error ? (
          <ErrorBanner error={search.error} />
        ) : results.length === 0 ? (
          <EmptyState
            title="No results"
            description="Try different words, or remove a filter. Documents and memories only match when they are about the same thing."
          />
        ) : (
          <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
            {results.map((result) => (
              <li key={`${result.type}-${result.id}`}>
                <Link href={TYPE_HREF[result.type]} className="block px-4 py-3 transition-colors hover:bg-muted/50">
                  <span className="flex items-center justify-between gap-3">
                    <span className="flex min-w-0 items-center gap-2">
                      <Badge>{TYPE_SINGULAR[result.type]}</Badge>
                      <span className="truncate text-sm font-medium">{result.title}</span>
                    </span>
                    {result.score !== null && (
                      <span className="shrink-0 text-xs text-muted-foreground">{Math.round(result.score * 100)}%</span>
                    )}
                  </span>
                  {result.snippet && (
                    <span className="mt-1 line-clamp-2 block text-sm text-muted-foreground">{result.snippet}</span>
                  )}
                  <Meta result={result} now={now} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}
