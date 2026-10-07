"use client";

import Link from "next/link";

import { Badge, Button, EmptyState, ErrorBanner, Spinner } from "@/components/ui";
import { useBriefing, useSuggestionMutations, useSuggestions } from "@/hooks/use-briefing";
import { ApiError } from "@/lib/api-client";
import { formatDue } from "@/lib/dates";
import { PRIORITY_LABELS, PRIORITY_TONES } from "@/lib/task-meta";
import type { MeetingBrief, SectionStatus, Suggestion, TaskBrief } from "@/lib/types";

function Section({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className="mt-8" aria-label={title}>
      <div className="mb-2 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

const card = "divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface";

function StatusNote({ status, what }: { status: SectionStatus; what: string }) {
  if (status === "ok") return null;
  const text = {
    not_connected: `Connect Google to see ${what}.`,
    needs_reauth: `Google access has expired, so ${what} can't be shown.`,
    unavailable: `Google didn't answer, so ${what} can't be shown right now.`,
  }[status];
  return (
    <p className="rounded-lg bg-muted px-3.5 py-2.5 text-sm text-muted-foreground">
      {text}{" "}
      <Link href="/integrations" className="font-medium text-accent hover:underline">
        {status === "not_connected" ? "Connections" : "Reconnect"}
      </Link>
    </p>
  );
}

function TaskList({ tasks, overdue }: { tasks: TaskBrief[]; overdue?: boolean }) {
  return (
    <ul className={card}>
      {tasks.map((t) => (
        <li key={t.id} className="flex items-center gap-3 px-4 py-2.5">
          <span className="min-w-0 flex-1 truncate text-sm">{t.title}</span>
          <Badge tone={PRIORITY_TONES[t.priority]}>{PRIORITY_LABELS[t.priority]}</Badge>
          {t.due_date && (
            <span className={`shrink-0 text-xs ${overdue ? "font-medium text-danger" : "text-muted-foreground"}`}>
              {formatDue(t.due_date)}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

function Meeting({ meeting }: { meeting: MeetingBrief }) {
  const time = (iso: string) => new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  return (
    <li className="px-4 py-3">
      <p className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{meeting.title}</span>
        {meeting.overlaps && <Badge tone="warning">Overlaps</Badge>}
      </p>
      <p className="mt-0.5 text-xs text-muted-foreground">
        {meeting.all_day ? "All day" : `${time(meeting.start)}–${time(meeting.end)}`}
        {meeting.location ? ` · ${meeting.location}` : ""}
      </p>
      {meeting.context.length > 0 && (
        <ul className="mt-2 space-y-1 border-l-2 border-border pl-3" aria-label={`Related to ${meeting.title}`}>
          {meeting.context.map((c) => (
            <li key={`${c.type}-${c.id}`} className="text-sm">
              <span className="text-xs uppercase text-muted-foreground">{c.type}</span> {c.title}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

function SuggestionCard({ suggestion }: { suggestion: Suggestion }) {
  const { accept, dismiss } = useSuggestionMutations();
  const busy = accept.isPending || dismiss.isPending;
  return (
    <li className="px-4 py-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium">{suggestion.title}</p>
          <p className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <Badge tone={PRIORITY_TONES[suggestion.priority]}>{PRIORITY_LABELS[suggestion.priority]}</Badge>
            {suggestion.due_date && <span>due {formatDue(suggestion.due_date)}</span>}
            <span>{suggestion.reason}</span>
          </p>
        </div>
        <div className="flex shrink-0 gap-1">
          <Button disabled={busy} onClick={() => accept.mutate(suggestion.id)}>
            Add task
          </Button>
          <Button variant="ghost" disabled={busy} onClick={() => dismiss.mutate(suggestion.id)}>
            Dismiss
          </Button>
        </div>
      </div>
      {(accept.error || dismiss.error) && (
        <div className="mt-2">
          <ErrorBanner error={accept.error ?? dismiss.error} />
        </div>
      )}
    </li>
  );
}

function Suggestions() {
  const suggestions = useSuggestions();
  const { scan } = useSuggestionMutations();
  const items = suggestions.data ?? [];
  const notConnected = scan.error instanceof ApiError && scan.error.code === "GOOGLE_NOT_CONNECTED";

  return (
    <Section
      title="Suggested tasks"
      action={
        <Button variant="secondary" disabled={scan.isPending} onClick={() => scan.mutate()}>
          {scan.isPending ? "Scanning…" : "Scan my email"}
        </Button>
      }
    >
      {notConnected ? (
        <StatusNote status="not_connected" what="suggestions from your email" />
      ) : scan.error ? (
        <ErrorBanner error={scan.error} />
      ) : null}
      {scan.data && (
        <p role="status" className="mb-2 text-sm text-muted-foreground">
          {scan.data.created === 0
            ? "Nothing new found in your email."
            : `Found ${scan.data.created} new suggestion${scan.data.created === 1 ? "" : "s"}.`}
        </p>
      )}
      {suggestions.isLoading ? (
        <Spinner />
      ) : items.length === 0 ? (
        !notConnected && (
          <p className="text-sm text-muted-foreground">
            Nothing waiting. Scanning looks through recent email for things people asked of you and for messages
            awaiting a reply. Nothing becomes a task until you add it.
          </p>
        )
      ) : (
        <ul className={card}>
          {items.map((s) => (
            <SuggestionCard key={s.id} suggestion={s} />
          ))}
        </ul>
      )}
    </Section>
  );
}

export default function TodayPage() {
  const briefing = useBriefing();
  const b = briefing.data;

  if (briefing.isLoading) return <Spinner label="Preparing your day" />;
  if (briefing.error || !b) return <ErrorBanner error={briefing.error} />;

  const date = new Date(`${b.date}T12:00:00`).toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
  const nothingPressing =
    b.priorities.length === 0 && b.due_today.length === 0 && b.meetings.length === 0 && b.follow_ups.length === 0;

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">Today</h1>
      <p className="mt-1 text-sm text-muted-foreground">{date}</p>

      {nothingPressing && (
        <div className="mt-6">
          <EmptyState
            title="Nothing pressing"
            description="No overdue or due tasks, nothing scheduled, and no follow-ups. Enjoy the quiet."
          />
        </div>
      )}

      {b.priorities.length > 0 && (
        <Section title="Focus on">
          <ol className={card}>
            {b.priorities.map((p, i) => (
              <li key={p.id} className="flex items-start gap-3 px-4 py-2.5">
                <span className="mt-0.5 w-5 shrink-0 text-sm font-semibold text-accent">{i + 1}</span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{p.title}</p>
                  <p className="text-xs text-muted-foreground">{p.reason}</p>
                </div>
              </li>
            ))}
          </ol>
        </Section>
      )}

      {b.suggested_actions.length > 0 && (
        <Section title="Suggested next steps">
          <ul className="space-y-1.5 text-sm">
            {b.suggested_actions.map((a) => (
              <li key={a} className="flex gap-2">
                <span aria-hidden="true" className="text-accent">
                  →
                </span>
                <span>{a}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section title="Meetings">
        <StatusNote status={b.meetings_status} what="today's meetings" />
        {b.meetings_status === "ok" &&
          (b.meetings.length === 0 ? (
            <p className="text-sm text-muted-foreground">No events on your calendar today.</p>
          ) : (
            <ul className={card}>
              {b.meetings.map((m) => (
                <Meeting key={m.id} meeting={m} />
              ))}
            </ul>
          ))}
      </Section>

      {b.overdue.length > 0 && (
        <Section title="Overdue">
          <TaskList tasks={b.overdue} overdue />
        </Section>
      )}
      {b.due_today.length > 0 && (
        <Section title="Due today">
          <TaskList tasks={b.due_today} />
        </Section>
      )}
      {b.due_tomorrow.length > 0 && (
        <Section title="Due tomorrow">
          <TaskList tasks={b.due_tomorrow} />
        </Section>
      )}

      <Suggestions />

      <Section title="Follow-ups">
        <StatusNote status={b.follow_ups_status} what="emails awaiting a reply" />
        {b.follow_ups.length === 0 ? (
          b.follow_ups_status === "ok" && <p className="text-sm text-muted-foreground">Nothing waiting on anyone.</p>
        ) : (
          <ul className={`${card} mt-2`}>
            {b.follow_ups.map((f, i) => (
              <li key={`${f.kind}-${i}`} className="px-4 py-2.5">
                <p className="flex items-center gap-2">
                  <Badge>{f.kind === "email" ? "Email" : f.kind === "task" ? "Task" : "Commitment"}</Badge>
                  <span className="truncate text-sm font-medium">{f.title}</span>
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {f.detail}
                  {f.days_waiting > 0 ? ` · ${f.days_waiting} day${f.days_waiting === 1 ? "" : "s"}` : ""}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Section>

      {b.recent_documents.length > 0 && (
        <Section title="Recently added documents">
          <ul className={card}>
            {b.recent_documents.map((d) => (
              <li key={d.id} className="px-4 py-2.5 text-sm">
                <Link href="/documents" className="hover:underline">
                  {d.filename}
                </Link>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </>
  );
}
