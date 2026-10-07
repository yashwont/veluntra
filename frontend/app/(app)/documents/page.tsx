"use client";

import { useRef, useState } from "react";

import { Badge, Button, EmptyState, ErrorBanner, Input, Spinner } from "@/components/ui";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useDocumentMutations, useDocumentSearch, useDocuments } from "@/hooks/use-documents";
import { useNow } from "@/hooks/use-now";
import { useWorkspace } from "@/hooks/use-workspace";
import { timeAgo } from "@/lib/dates";
import type { DocumentItem, DocumentStatus } from "@/lib/types";
import { documentDownloadUrl } from "@/services/documents";

const PAGE_SIZE = 20;
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024; // keep in step with the backend's MAX_UPLOAD_BYTES
const ACCEPT = ".txt,.md,.pdf,.docx";

const STATUS: Record<DocumentStatus, { label: string; tone: "neutral" | "accent" | "danger" | "success" }> = {
  pending: { label: "Queued", tone: "neutral" },
  processing: { label: "Processing…", tone: "accent" },
  ready: { label: "Ready", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
};

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function DocumentRow({ doc, workspaceId, now }: { doc: DocumentItem; workspaceId: string; now: number }) {
  const { reprocess, remove } = useDocumentMutations();
  const [confirming, setConfirming] = useState(false);
  const status = STATUS[doc.status];
  const busy = doc.status === "pending" || doc.status === "processing";

  return (
    <li className="px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{doc.filename}</p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            <Badge tone={status.tone}>{status.label}</Badge>
            <span>{formatSize(doc.size_bytes)}</span>
            {doc.status === "ready" && (
              <span>
                {doc.chunk_count} {doc.chunk_count === 1 ? "passage" : "passages"}
              </span>
            )}
            <span>{timeAgo(doc.created_at, now)}</span>
          </p>
          {doc.status === "failed" && doc.error && (
            <p role="alert" className="mt-1.5 text-sm text-danger">
              {doc.error}
            </p>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-1">
          {confirming ? (
            <>
              <Button
                variant="danger"
                disabled={remove.isPending}
                onClick={() => remove.mutate(doc.id, { onSettled: () => setConfirming(false) })}
              >
                Delete
              </Button>
              <Button variant="ghost" onClick={() => setConfirming(false)}>
                Cancel
              </Button>
            </>
          ) : (
            <>
              {doc.status === "failed" && (
                <Button variant="secondary" disabled={reprocess.isPending} onClick={() => reprocess.mutate(doc.id)}>
                  Retry
                </Button>
              )}
              <a
                href={documentDownloadUrl(workspaceId, doc.id)}
                download
                className="rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                Download
              </a>
              <Button variant="ghost" disabled={busy} onClick={() => setConfirming(true)}>
                Delete
              </Button>
            </>
          )}
        </div>
      </div>
      {(reprocess.error || remove.error) && (
        <div className="mt-2">
          <ErrorBanner error={reprocess.error ?? remove.error} />
        </div>
      )}
    </li>
  );
}

function SearchResults({ query }: { query: string }) {
  const results = useDocumentSearch(query);

  if (results.isLoading) return <Spinner label="Searching" />;
  if (results.error) return <ErrorBanner error={results.error} />;
  const hits = results.data ?? [];
  if (hits.length === 0) {
    return (
      <EmptyState
        title="No matching passages"
        description="Only documents that have finished processing are searched. Try different words."
      />
    );
  }
  return (
    <ul className="space-y-3">
      {hits.map((hit) => (
        <li key={`${hit.document_id}-${hit.chunk_index}`} className="rounded-xl border border-border bg-surface p-4">
          <p className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
            <span className="truncate font-medium text-foreground">{hit.filename}</span>
            <span className="shrink-0">match {Math.round(hit.score * 100)}%</span>
          </p>
          <p className="mt-2 line-clamp-6 whitespace-pre-line text-sm">{hit.content}</p>
        </li>
      ))}
    </ul>
  );
}

export default function DocumentsPage() {
  const now = useNow();
  const { workspaceId } = useWorkspace();
  const fileInput = useRef<HTMLInputElement>(null);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [dragging, setDragging] = useState(false);
  const [uploadErrors, setUploadErrors] = useState<string[]>([]);

  const q = useDebouncedValue(search.trim(), 400);
  const documents = useDocuments({ limit: PAGE_SIZE, offset });
  const { upload } = useDocumentMutations();

  const items = documents.data?.items ?? [];
  const total = documents.data?.total ?? 0;

  async function uploadFiles(files: FileList | File[]) {
    const errors: string[] = [];
    setOffset(0);
    for (const file of Array.from(files)) {
      if (file.size > MAX_UPLOAD_BYTES) {
        errors.push(`${file.name}: larger than ${MAX_UPLOAD_BYTES / (1024 * 1024)} MB.`);
        continue;
      }
      try {
        await upload.mutateAsync(file);
      } catch (error) {
        errors.push(`${file.name}: ${error instanceof Error ? error.message : "Upload failed."}`);
      }
    }
    setUploadErrors(errors);
  }

  return (
    <>
      <div className="mb-6 flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">Documents</h1>
        <Button onClick={() => fileInput.current?.click()} disabled={upload.isPending}>
          {upload.isPending ? "Uploading…" : "Upload"}
        </Button>
        <input
          ref={fileInput}
          type="file"
          accept={ACCEPT}
          multiple
          hidden
          onChange={(e) => {
            if (e.target.files?.length) void uploadFiles(e.target.files);
            e.target.value = ""; // allow picking the same file again
          }}
        />
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (e.dataTransfer.files.length) void uploadFiles(e.dataTransfer.files);
        }}
        className={`rounded-xl border border-dashed px-4 py-5 text-center text-sm transition-colors ${
          dragging ? "border-accent bg-accent-soft text-accent" : "border-border text-muted-foreground"
        }`}
      >
        Drop files here, or use Upload. TXT, MD, PDF or DOCX, up to {MAX_UPLOAD_BYTES / (1024 * 1024)} MB.
      </div>

      {uploadErrors.length > 0 && (
        <div role="alert" className="mt-3 space-y-1 rounded-lg bg-danger-soft px-3.5 py-2.5 text-sm text-danger">
          {uploadErrors.map((message) => (
            <p key={message}>{message}</p>
          ))}
        </div>
      )}

      <div className="mt-6">
        <Input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search inside your documents…"
          aria-label="Search document contents"
          maxLength={500}
        />
      </div>

      <div className="mt-4">
        {q ? (
          <SearchResults query={q} />
        ) : documents.isLoading || !workspaceId ? (
          <Spinner />
        ) : documents.error ? (
          <ErrorBanner error={documents.error} />
        ) : items.length === 0 ? (
          <EmptyState title="No documents yet" description="Upload a file to make it searchable." />
        ) : (
          <>
            <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
              {items.map((doc) => (
                <DocumentRow key={doc.id} doc={doc} workspaceId={workspaceId} now={now} />
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
    </>
  );
}
