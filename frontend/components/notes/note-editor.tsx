"use client";

import { useState } from "react";

import { Button, ErrorBanner, Field, Input, Spinner, Textarea } from "@/components/ui";
import { useNote, useNoteMutations } from "@/hooks/use-notes";
import { ApiError } from "@/lib/api-client";
import type { Note } from "@/lib/types";

function NoteForm({
  note,
  onSaved,
  onDeleted,
  onClose,
}: {
  note?: Note;
  onSaved: (id: string) => void;
  onDeleted: () => void;
  onClose: () => void;
}) {
  const { create, update, remove } = useNoteMutations();
  const [title, setTitle] = useState(note?.title ?? "");
  const [content, setContent] = useState(note?.content ?? "");
  const [tags, setTags] = useState(note?.tags.join(", ") ?? "");

  const mutation = note ? update : create;
  const error = mutation.error instanceof ApiError ? mutation.error : null;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const fields = {
      title,
      content,
      tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
    };
    if (note) {
      update.mutate({ id: note.id, patch: fields }, { onSuccess: (saved) => onSaved(saved.id) });
    } else {
      create.mutate(fields, { onSuccess: (saved) => onSaved(saved.id) });
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <Field label="Title" htmlFor="note-title" error={error?.fieldError("title")}>
        <Input
          id="note-title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={300}
          required
          autoFocus={!note}
        />
      </Field>
      <Field label="Content" htmlFor="note-content" error={error?.fieldError("content")}>
        <Textarea
          id="note-content"
          rows={14}
          value={content}
          onChange={(e) => setContent(e.target.value)}
        />
      </Field>
      <Field
        label="Tags"
        htmlFor="note-tags"
        error={error?.fieldError("tags")}
        hint="Separate with commas, e.g. work, ideas"
      >
        <Input id="note-tags" value={tags} onChange={(e) => setTags(e.target.value)} />
      </Field>

      {!error?.details.length && <ErrorBanner error={mutation.error ?? remove.error} />}
      {update.isSuccess && !update.isPending && (
        <p role="status" className="text-sm text-success">
          Saved.
        </p>
      )}

      <div className="flex items-center gap-2">
        {note && (
          <Button
            variant="danger"
            disabled={remove.isPending}
            onClick={() => {
              if (confirm(`Delete "${note.title}"? This can't be undone.`)) {
                remove.mutate(note.id, { onSuccess: onDeleted });
              }
            }}
          >
            Delete
          </Button>
        )}
        <div className="ml-auto flex gap-2">
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
          <Button type="submit" disabled={mutation.isPending || !title.trim()}>
            {mutation.isPending ? "Saving…" : note ? "Save" : "Create note"}
          </Button>
        </div>
      </div>
    </form>
  );
}

/** Loads a note by id (or starts a blank one for "new") and shows its form. */
export function NoteEditor({
  noteId,
  onSaved,
  onDeleted,
  onClose,
}: {
  noteId: string | "new";
  onSaved: (id: string) => void;
  onDeleted: () => void;
  onClose: () => void;
}) {
  const note = useNote(noteId === "new" ? null : noteId);

  if (noteId === "new") {
    return <NoteForm key="new" onSaved={onSaved} onDeleted={onDeleted} onClose={onClose} />;
  }
  if (note.isLoading) return <Spinner />;
  if (note.error || !note.data) return <ErrorBanner error={note.error ?? new Error("Note not found")} />;

  // Keyed by id only: a background refetch must not overwrite what the user is typing
  return (
    <NoteForm
      key={note.data.id}
      note={note.data}
      onSaved={onSaved}
      onDeleted={onDeleted}
      onClose={onClose}
    />
  );
}
