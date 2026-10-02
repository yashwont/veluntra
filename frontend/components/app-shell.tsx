"use client";

import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button, ErrorBanner, Spinner } from "@/components/ui";
import { useMe } from "@/hooks/use-me";
import { useWorkspace } from "@/hooks/use-workspace";
import { logout } from "@/services/auth";

const NAV = [
  { href: "/", label: "Home", icon: "M3 11.5 12 4l9 7.5M5 10v10h5v-6h4v6h5V10" },
  { href: "/tasks", label: "Tasks", icon: "M9 11.5 11 13.5 15.5 9M5 4h14v16H5z" },
  { href: "/notes", label: "Notes", icon: "M6 3h9l4 4v14H6zM14 3v5h5M9 13h7M9 17h5" },
] as const;

function NavIcon({ path }: { path: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className="size-[18px] shrink-0"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={path} />
    </svg>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const me = useMe();
  const { isLoading: workspaceLoading, error: workspaceError } = useWorkspace();

  const signOut = useMutation({
    mutationFn: logout,
    // A full page load, not router.push: it drops every cached query at once, so
    // nothing in this still-mounted shell refetches against the signed-out API.
    onSettled: () => window.location.assign(new URL("/login", window.location.origin)),
  });

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="flex shrink-0 flex-col gap-1 border-b border-border bg-surface px-3 py-3 md:sticky md:top-0 md:h-screen md:w-60 md:border-r md:border-b-0 md:py-5">
        <div className="flex items-center justify-between px-2 md:mb-4 md:block">
          <p className="text-lg font-semibold tracking-tight">Veluntra</p>
          <Button
            variant="ghost"
            className="md:hidden"
            onClick={() => signOut.mutate()}
            disabled={signOut.isPending}
          >
            Sign out
          </Button>
        </div>

        <nav aria-label="Main" className="flex gap-1 md:flex-col">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isActive(item.href) ? "page" : undefined}
              className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                isActive(item.href)
                  ? "bg-accent-soft text-accent"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              <NavIcon path={item.icon} />
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="mt-auto hidden border-t border-border px-2 pt-4 md:block">
          <p className="truncate text-sm font-medium">{me.data?.full_name ?? "…"}</p>
          <p className="truncate text-xs text-muted-foreground">{me.data?.email}</p>
          <Button
            variant="ghost"
            className="-ml-3 mt-2"
            onClick={() => signOut.mutate()}
            disabled={signOut.isPending}
          >
            Sign out
          </Button>
        </div>
      </aside>

      <main className="min-w-0 flex-1 px-4 py-6 md:px-10 md:py-8">
        <div className="mx-auto max-w-4xl">
          {workspaceLoading ? (
            <Spinner />
          ) : workspaceError ? (
            <ErrorBanner error={workspaceError} />
          ) : (
            children
          )}
        </div>
      </main>
    </div>
  );
}
