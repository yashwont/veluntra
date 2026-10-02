import type { Task } from "@/lib/types";

/** Local calendar date as YYYY-MM-DD (the format <input type="date"> uses). */
export function toDateInput(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** A due *date* means "by the end of that day" in the user's timezone. */
export function endOfDayIso(dateInput: string): string {
  return new Date(`${dateInput}T23:59:59`).toISOString();
}

export function formatDue(iso: string): string {
  const d = new Date(iso);
  const sameYear = d.getFullYear() === new Date().getFullYear();
  const date = d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: sameYear ? undefined : "numeric",
  });
  const isEndOfDay = d.getHours() === 23 && d.getMinutes() === 59;
  if (isEndOfDay) return date;
  return `${date}, ${d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}`;
}

export function isOverdue(task: Pick<Task, "due_date" | "status">, now: number): boolean {
  return (
    task.due_date !== null &&
    (task.status === "todo" || task.status === "in_progress") &&
    new Date(task.due_date).getTime() < now
  );
}

export function timeAgo(iso: string, now: number): string {
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
