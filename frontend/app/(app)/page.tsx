"use client";

import Link from "next/link";
import { useState } from "react";

import { Badge, EmptyState, ErrorBanner, Spinner } from "@/components/ui";
import { useMe } from "@/hooks/use-me";
import { useNotes } from "@/hooks/use-notes";
import { useNow } from "@/hooks/use-now";
import { useTasks } from "@/hooks/use-tasks";
import { formatDue, timeAgo } from "@/lib/dates";
import { PRIORITY_LABELS, PRIORITY_TONES } from "@/lib/task-meta";
import type { Task } from "@/lib/types";

const WEEK_MS = 7 * 24 * 60 * 60 * 1000;

function greeting(hour: number) {
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function Stat({ label, value, tone }: { label: string; value: number | undefined; tone?: "danger" }) {
  return (
    <div className="rounded-xl border border-border bg-surface px-4 py-3">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${tone === "danger" && value ? "text-danger" : ""}`}>
        {value ?? "–"}
      </p>
    </div>
  );
}

function TaskLine({ task, overdue }: { task: Task; overdue?: boolean }) {
  return (
    <li className="flex items-center gap-3 px-4 py-2.5">
      <span className="min-w-0 flex-1 truncate text-sm">{task.title}</span>
      <Badge tone={PRIORITY_TONES[task.priority]}>{PRIORITY_LABELS[task.priority]}</Badge>
      {task.due_date && (
        <span className={`shrink-0 text-xs ${overdue ? "font-medium text-danger" : "text-muted-foreground"}`}>
          {formatDue(task.due_date)}
        </span>
      )}
    </li>
  );
}

function Section({
  title,
  href,
  children,
}: {
  title: string;
  href: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-8">
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">{title}</h2>
        <Link href={href} className="text-sm text-accent hover:underline">
          View all
        </Link>
      </div>
      {children}
    </section>
  );
}

export default function HomePage() {
  const now = useNow();
  // Fixed for the lifetime of the page so query keys stay stable between renders
  const [weekWindow] = useState(() => {
    const start = Date.now();
    return { after: new Date(start).toISOString(), before: new Date(start + WEEK_MS).toISOString() };
  });

  const me = useMe();
  const overdue = useTasks({ overdue: true, limit: 5 });
  const inProgress = useTasks({ status: "in_progress", limit: 1 });
  const upcoming = useTasks({ due_after: weekWindow.after, due_before: weekWindow.before, limit: 50 });
  const notes = useNotes({ limit: 5 });

  const firstName = me.data?.full_name.split(" ")[0];
  const comingUp = (upcoming.data?.items ?? []).filter(
    (t) => t.status === "todo" || t.status === "in_progress",
  );

  if (overdue.isLoading || upcoming.isLoading || notes.isLoading) return <Spinner />;
  const error = overdue.error ?? upcoming.error ?? notes.error;

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">
        {greeting(new Date(now).getHours())}
        {firstName ? `, ${firstName}` : ""}
      </h1>
      <p className="mt-1 text-sm text-muted-foreground">Here&apos;s what needs your attention.</p>

      {error && (
        <div className="mt-4">
          <ErrorBanner error={error} />
        </div>
      )}

      <div className="mt-6 grid grid-cols-3 gap-3">
        <Stat label="Overdue" value={overdue.data?.total} tone="danger" />
        <Stat label="In progress" value={inProgress.data?.total} />
        <Stat label="Notes" value={notes.data?.total} />
      </div>

      <Section title="Overdue" href="/tasks">
        {(overdue.data?.items.length ?? 0) === 0 ? (
          <EmptyState title="Nothing overdue" description="You're all caught up." />
        ) : (
          <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
            {overdue.data?.items.map((t) => <TaskLine key={t.id} task={t} overdue />)}
          </ul>
        )}
      </Section>

      <Section title="Due in the next 7 days" href="/tasks">
        {comingUp.length === 0 ? (
          <EmptyState title="Nothing due this week" />
        ) : (
          <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
            {comingUp.map((t) => <TaskLine key={t.id} task={t} />)}
          </ul>
        )}
      </Section>

      <Section title="Recent notes" href="/notes">
        {(notes.data?.items.length ?? 0) === 0 ? (
          <EmptyState title="No notes yet" />
        ) : (
          <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
            {notes.data?.items.map((n) => (
              <li key={n.id} className="flex items-center gap-3 px-4 py-2.5">
                <span className="min-w-0 flex-1 truncate text-sm">{n.title}</span>
                <span className="shrink-0 text-xs text-muted-foreground">{timeAgo(n.updated_at, now)}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </>
  );
}
