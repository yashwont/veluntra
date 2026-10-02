"use client";

import { useEffect, useRef } from "react";

import { ApiError } from "@/lib/api-client";

function cx(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

// --- Button -----------------------------------------------------------------

const buttonVariants = {
  primary: "bg-accent text-accent-foreground hover:bg-accent-hover",
  secondary: "border border-border bg-surface hover:bg-muted",
  ghost: "hover:bg-muted text-muted-foreground hover:text-foreground",
  danger: "text-danger hover:bg-danger-soft",
} as const;

export function Button({
  variant = "primary",
  className,
  type = "button",
  ...props
}: React.ComponentProps<"button"> & { variant?: keyof typeof buttonVariants }) {
  return (
    <button
      type={type}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition-colors",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
        "disabled:cursor-not-allowed disabled:opacity-50",
        buttonVariants[variant],
        className,
      )}
      {...props}
    />
  );
}

// --- Form controls -----------------------------------------------------------

// Width is not part of the shared style: Input/Textarea fill their container,
// while Select sizes to its content unless the caller passes e.g. "w-full".
const controlClass =
  "rounded-lg border border-border bg-surface px-3 py-2 text-sm placeholder:text-muted-foreground " +
  "focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25 disabled:opacity-60";

export function Input({ className, ...props }: React.ComponentProps<"input">) {
  return <input className={cx(controlClass, "w-full", className)} {...props} />;
}

export function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return <textarea className={cx(controlClass, "w-full resize-y", className)} {...props} />;
}

export function Select({ className, ...props }: React.ComponentProps<"select">) {
  return <select className={cx(controlClass, className)} {...props} />;
}

export function Field({
  label,
  error,
  hint,
  htmlFor,
  children,
}: {
  label: string;
  error?: string;
  hint?: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="text-sm font-medium">
        {label}
      </label>
      {children}
      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : hint ? (
        <p className="text-xs text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}

// --- Feedback -----------------------------------------------------------------

export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof ApiError ? error.message : "Something went wrong.";
  return (
    <div role="alert" className="rounded-lg bg-danger-soft px-3.5 py-2.5 text-sm text-danger">
      {message}
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" aria-label={label} className="flex justify-center py-10">
      <div className="size-5 animate-spin rounded-full border-2 border-border border-t-accent" />
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed border-border px-6 py-12 text-center">
      <p className="font-medium">{title}</p>
      {description && <p className="mt-1 max-w-sm text-sm text-muted-foreground">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Badge({
  tone = "neutral",
  children,
}: {
  tone?: "neutral" | "accent" | "danger" | "warning" | "success";
  children: React.ReactNode;
}) {
  const tones = {
    neutral: "bg-muted text-muted-foreground",
    accent: "bg-accent-soft text-accent",
    danger: "bg-danger-soft text-danger",
    warning: "bg-warning/15 text-warning",
    success: "bg-success/15 text-success",
  } as const;
  return (
    <span className={cx("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium", tones[tone])}>
      {children}
    </span>
  );
}

// --- Modal (native <dialog>: focus trap, Esc to close, backdrop for free) ----------

export function Modal({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      aria-label={title}
      className="m-auto w-[min(32rem,calc(100vw-2rem))] rounded-2xl border border-border bg-surface p-0 text-foreground shadow-xl"
    >
      {/* Mounted only while open, so every open starts with a fresh form */}
      {open && (
        <div className="p-6">
          <h2 className="mb-4 text-lg font-semibold">{title}</h2>
          {children}
        </div>
      )}
    </dialog>
  );
}
