import { type NextRequest, NextResponse } from "next/server";

import { REFRESH_COOKIE } from "@/lib/server/session";

/**
 * Optimistic routing only: sends signed-out visitors to /login and signed-in
 * ones away from it. It checks that a session cookie *exists*, nothing more.
 * Real authentication happens in the API route handlers and the backend.
 */

const AUTH_PAGES = new Set(["/login", "/register"]);

export function proxy(request: NextRequest) {
  const hasSession = request.cookies.has(REFRESH_COOKIE);
  const { pathname } = request.nextUrl;

  if (AUTH_PAGES.has(pathname)) {
    return hasSession
      ? NextResponse.redirect(new URL("/", request.url))
      : NextResponse.next();
  }
  if (!hasSession) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  return NextResponse.next();
}

export const config = {
  // Pages only: skip API routes, Next internals and static files
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
