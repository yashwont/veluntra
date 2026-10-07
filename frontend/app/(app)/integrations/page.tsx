"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Badge, Button, EmptyState, ErrorBanner, Input, Spinner } from "@/components/ui";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import {
  useCalendar,
  useDriveSearch,
  useEmailSearch,
  useIntegrationMutations,
  useIntegrations,
} from "@/hooks/use-integrations";
import type { CalendarEvent, IntegrationAccount } from "@/lib/types";

const OUTCOMES: Record<string, { tone: "success" | "danger" | "warning"; text: string }> = {
  connected: { tone: "success", text: "Google connected." },
  denied: { tone: "warning", text: "You cancelled at Google, so nothing was connected." },
  error: { tone: "danger", text: "Google couldn't be connected. Please try again." },
};

function timeLabel(event: CalendarEvent): string {
  const start = new Date(event.start);
  const day = start.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
  if (event.all_day) return `${day} · all day`;
  const time = (d: Date) => d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  return `${day} · ${time(start)}–${time(new Date(event.end))}`;
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6" aria-label={title}>
      <h2 className="mb-2 text-sm font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function CalendarPanel() {
  const calendar = useCalendar(true);
  const events = calendar.data?.events ?? [];
  const clashing = new Set((calendar.data?.conflicts ?? []).flat());

  return (
    <Panel title="Next 7 days">
      {calendar.isLoading ? (
        <Spinner />
      ) : calendar.error ? (
        <ErrorBanner error={calendar.error} />
      ) : events.length === 0 ? (
        <EmptyState title="Nothing scheduled" description="Your calendar is clear for the next week." />
      ) : (
        <>
          {clashing.size > 0 && (
            <p role="status" className="mb-2 rounded-lg bg-warning/15 px-3 py-2 text-sm text-warning">
              {calendar.data!.conflicts.length} scheduling {calendar.data!.conflicts.length === 1 ? "conflict" : "conflicts"}{" "}
              found: overlapping events are marked below.
            </p>
          )}
          <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
            {events.map((event) => (
              <li key={event.id} className="px-4 py-2.5">
                <p className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">{event.title}</span>
                  {clashing.has(event.id) && <Badge tone="warning">Overlaps</Badge>}
                  {event.declined && <Badge>Declined</Badge>}
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {timeLabel(event)}
                  {event.location ? ` · ${event.location}` : ""}
                </p>
              </li>
            ))}
          </ul>
        </>
      )}
    </Panel>
  );
}

function EmailPanel() {
  const [input, setInput] = useState("");
  const q = useDebouncedValue(input.trim(), 400);
  const emails = useEmailSearch(q, true);

  return (
    <Panel title="Email">
      <Input
        type="search"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder="Search your email (e.g. from:ram invoice)…"
        aria-label="Search email"
        maxLength={500}
      />
      <div className="mt-3">
        {emails.isLoading ? (
          <Spinner />
        ) : emails.error ? (
          <ErrorBanner error={emails.error} />
        ) : (emails.data ?? []).length === 0 ? (
          <EmptyState title="No emails found" />
        ) : (
          <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
            {emails.data!.map((m) => (
              <li key={m.id} className="px-4 py-2.5">
                <p className="truncate text-sm font-medium">{m.subject}</p>
                <p className="truncate text-xs text-muted-foreground">{m.sender}</p>
                {m.snippet && <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{m.snippet}</p>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Panel>
  );
}

function DrivePanel() {
  const [input, setInput] = useState("");
  const q = useDebouncedValue(input.trim(), 400);
  const files = useDriveSearch(q, true);
  const { importFile } = useIntegrationMutations();
  const [imported, setImported] = useState<Set<string>>(new Set());

  return (
    <Panel title="Drive">
      <Input
        type="search"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder="Search your Drive…"
        aria-label="Search Drive"
        maxLength={300}
      />
      <div className="mt-3">
        {files.isLoading ? (
          <Spinner />
        ) : files.error ? (
          <ErrorBanner error={files.error} />
        ) : (files.data ?? []).length === 0 ? (
          <EmptyState title="No files found" />
        ) : (
          <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
            {files.data!.map((file) => (
              <li key={file.id} className="flex items-center justify-between gap-3 px-4 py-2.5">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{file.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {file.modified_at ? new Date(file.modified_at).toLocaleDateString() : ""}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  {file.link && (
                    <a
                      href={file.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
                    >
                      Open
                    </a>
                  )}
                  {imported.has(file.id) ? (
                    <Link href="/documents" className="px-3 py-2 text-sm font-medium text-accent">
                      Imported →
                    </Link>
                  ) : (
                    <Button
                      variant="secondary"
                      disabled={importFile.isPending}
                      onClick={() =>
                        importFile.mutate(file.id, { onSuccess: () => setImported((s) => new Set(s).add(file.id)) })
                      }
                    >
                      Import
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
        {importFile.error && (
          <div className="mt-2">
            <ErrorBanner error={importFile.error} />
          </div>
        )}
        <p className="mt-2 text-xs text-muted-foreground">
          Importing copies a Google Doc, PDF, DOCX, TXT or MD file into Documents so it becomes searchable. The original
          is never changed.
        </p>
      </div>
    </Panel>
  );
}

function AccountCard({ account }: { account: IntegrationAccount }) {
  const { connect, disconnect } = useIntegrationMutations();
  const [confirming, setConfirming] = useState(false);
  const services = [
    ["Gmail", account.gmail],
    ["Calendar", account.calendar],
    ["Drive", account.drive],
  ] as const;

  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium">Google</p>
          <p className="truncate text-sm text-muted-foreground">{account.account_email ?? "Connected account"}</p>
          <p className="mt-2 flex flex-wrap gap-1.5">
            {services.map(([name, granted]) => (
              <Badge key={name} tone={granted ? "success" : "neutral"}>
                {name}
                {granted ? "" : " (not allowed)"}
              </Badge>
            ))}
          </p>
        </div>
        <div className="flex items-center gap-1">
          {account.status === "needs_reauth" && (
            <Button disabled={connect.isPending} onClick={() => connect.mutate()}>
              Reconnect
            </Button>
          )}
          {confirming ? (
            <>
              <Button
                variant="danger"
                disabled={disconnect.isPending}
                onClick={() => disconnect.mutate(account.id, { onSettled: () => setConfirming(false) })}
              >
                Disconnect
              </Button>
              <Button variant="ghost" onClick={() => setConfirming(false)}>
                Cancel
              </Button>
            </>
          ) : (
            <Button variant="ghost" onClick={() => setConfirming(true)}>
              Disconnect
            </Button>
          )}
        </div>
      </div>
      {account.status === "needs_reauth" && (
        <p role="alert" className="mt-3 rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">
          Google no longer accepts this connection (access was revoked or has expired). Reconnect to keep using it.
        </p>
      )}
      <ErrorBanner error={connect.error ?? disconnect.error} />
    </div>
  );
}

function OutcomeBanner() {
  const result = useSearchParams().get("google");
  const banner = result ? OUTCOMES[result] : undefined;
  if (!banner) return null;
  const tones = {
    success: "bg-success/15 text-success",
    warning: "bg-warning/15 text-warning",
    danger: "bg-danger-soft text-danger",
  };
  return (
    <p role="status" className={`mb-4 rounded-lg px-3.5 py-2.5 text-sm ${tones[banner.tone]}`}>
      {banner.text}
    </p>
  );
}

export default function IntegrationsPage() {
  const integrations = useIntegrations();
  const { connect } = useIntegrationMutations();

  const data = integrations.data;
  const account = data?.accounts[0];

  return (
    <>
      <h1 className="mb-2 text-2xl font-semibold tracking-tight">Connections</h1>
      <p className="mb-6 max-w-2xl text-sm text-muted-foreground">
        Let the assistant look at your Gmail, Google Calendar and Drive. Access is read-only: Veluntra can read, but
        never send, create, change or delete anything in Google. You can disconnect at any time.
      </p>

      {/* Google sends the browser back here with the result in the address */}
      <Suspense>
        <OutcomeBanner />
      </Suspense>

      {integrations.isLoading ? (
        <Spinner />
      ) : integrations.error ? (
        <ErrorBanner error={integrations.error} />
      ) : !data?.google_configured ? (
        <EmptyState
          title="Google isn't set up on this server"
          description="An administrator needs to add a Google client ID and secret first. The steps are in docs/GOOGLE_SETUP.md."
        />
      ) : !account ? (
        <EmptyState
          title="Google isn't connected"
          description="You'll be sent to Google to choose what to allow, then brought back here."
          action={
            <Button disabled={connect.isPending} onClick={() => connect.mutate()}>
              {connect.isPending ? "Opening Google…" : "Connect Google"}
            </Button>
          }
        />
      ) : (
        <>
          <AccountCard account={account} />
          {account.status === "active" && (
            <>
              {account.calendar && <CalendarPanel />}
              {account.gmail && <EmailPanel />}
              {account.drive && <DrivePanel />}
            </>
          )}
        </>
      )}
      {connect.error && !account && <ErrorBanner error={connect.error} />}
    </>
  );
}
