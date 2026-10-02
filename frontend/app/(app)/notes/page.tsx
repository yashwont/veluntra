"use client";

import { useState } from "react";

import { NoteEditor } from "@/components/notes/note-editor";
import { Badge, Button, EmptyState, ErrorBanner, Input, Spinner } from "@/components/ui";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useNotes } from "@/hooks/use-notes";
import { useNow } from "@/hooks/use-now";
import { timeAgo } from "@/lib/dates";

const PAGE_SIZE = 20;

export default function NotesPage() {
  const now = useNow();
  const [search, setSearch] = useState("");
  const [tag, setTag] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string | "new" | null>(null);

  const q = useDebouncedValue(search.trim(), 300);
  const notes = useNotes({ q: q || undefined, tag: tag ? [tag] : undefined, limit: PAGE_SIZE, offset });

  const items = notes.data?.items ?? [];
  const total = notes.data?.total ?? 0;
  // Tag chips come from the notes currently shown (plus the active filter)
  const visibleTags = [...new Set([...(tag ? [tag] : []), ...items.flatMap((n) => n.tags)])].sort();
  const searching = !!q || !!tag;

  return (
    <>
      <div className="mb-6 flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">Notes</h1>
        <Button onClick={() => setSelected("new")}>New note</Button>
      </div>

      <div className="grid gap-6 md:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
        {/* List pane: hidden on small screens while a note is open */}
        <section className={selected !== null ? "hidden md:block" : ""} aria-label="Notes list">
          <Input
            type="search"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setOffset(0);
            }}
            placeholder="Search notes…"
            aria-label="Search notes"
            maxLength={200}
          />

          {visibleTags.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {visibleTags.map((t) => (
                <button
                  key={t}
                  type="button"
                  aria-pressed={tag === t}
                  onClick={() => {
                    setTag(tag === t ? null : t);
                    setOffset(0);
                  }}
                  className={`rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
                    tag === t
                      ? "bg-accent text-accent-foreground"
                      : "bg-muted text-muted-foreground hover:text-foreground"
                  }`}
                >
                  #{t}
                </button>
              ))}
            </div>
          )}

          <div className="mt-4">
            {notes.isLoading ? (
              <Spinner />
            ) : notes.error ? (
              <ErrorBanner error={notes.error} />
            ) : items.length === 0 ? (
              <EmptyState
                title={searching ? "No notes found" : "No notes yet"}
                description={searching ? "Try different words, or clear the tag filter." : "Create your first note."}
              />
            ) : (
              <>
                <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
                  {items.map((note) => (
                    <li key={note.id}>
                      <button
                        type="button"
                        onClick={() => setSelected(note.id)}
                        aria-current={selected === note.id ? "true" : undefined}
                        className={`block w-full px-4 py-3 text-left transition-colors hover:bg-muted/50 ${
                          selected === note.id ? "bg-accent-soft" : ""
                        }`}
                      >
                        <span className="block truncate text-sm font-medium">{note.title}</span>
                        {note.preview && (
                          <span className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">{note.preview}</span>
                        )}
                        <span className="mt-1.5 flex flex-wrap items-center gap-1.5">
                          {note.tags.slice(0, 3).map((t) => (
                            <Badge key={t}>#{t}</Badge>
                          ))}
                          <span className="text-xs text-muted-foreground">{timeAgo(note.updated_at, now)}</span>
                        </span>
                      </button>
                    </li>
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
        </section>

        {/* Editor pane */}
        <section className={selected === null ? "hidden md:block" : ""} aria-label="Note editor">
          {selected === null ? (
            <EmptyState title="Select a note" description="Pick a note from the list, or create a new one." />
          ) : (
            <div className="rounded-xl border border-border bg-surface p-5">
              <NoteEditor
                noteId={selected}
                onSaved={setSelected}
                onDeleted={() => setSelected(null)}
                onClose={() => setSelected(null)}
              />
            </div>
          )}
        </section>
      </div>
    </>
  );
}
