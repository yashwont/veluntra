import "server-only";

import { NextResponse } from "next/server";

/**
 * Server-side session handling for the backend-for-frontend (BFF) layer.
 *
 * The browser never sees an API token. Both tokens live in httpOnly cookies set
 * here, so JavaScript on the page (including any XSS) cannot read them.
 */

export const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export const ACCESS_COOKIE = "veluntra_access";
export const REFRESH_COOKIE = "veluntra_refresh";

// Matches the backend's REFRESH_TOKEN_EXPIRE_DAYS default
const REFRESH_MAX_AGE_SECONDS = 14 * 24 * 60 * 60;

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

const cookieBase = {
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  sameSite: "lax" as const,
  path: "/",
};

export function setSessionCookies(response: NextResponse, tokens: TokenPair) {
  response.cookies.set(ACCESS_COOKIE, tokens.access_token, {
    ...cookieBase,
    maxAge: tokens.expires_in,
  });
  response.cookies.set(REFRESH_COOKIE, tokens.refresh_token, {
    ...cookieBase,
    maxAge: REFRESH_MAX_AGE_SECONDS,
  });
}

export function clearSessionCookies(response: NextResponse) {
  response.cookies.set(ACCESS_COOKIE, "", { ...cookieBase, maxAge: 0 });
  response.cookies.set(REFRESH_COOKIE, "", { ...cookieBase, maxAge: 0 });
}

export function errorResponse(
  status: number,
  code: string,
  message: string,
): NextResponse {
  return NextResponse.json({ error: { code, message } }, { status });
}

/** 401 that also clears the session cookies, so the client lands on /login cleanly. */
export function unauthenticatedResponse(): NextResponse {
  const response = errorResponse(
    401,
    "NOT_AUTHENTICATED",
    "Authentication is required.",
  );
  clearSessionCookies(response);
  return response;
}

/**
 * CSRF defence in depth (cookies are already SameSite=Lax): state-changing
 * requests must come from this site's own pages. Browsers always send `Origin`
 * on cross-origin and same-origin non-GET fetches.
 */
export function isSameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  const host = request.headers.get("host");
  if (!origin || !host) return false;
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

// --- Token refresh ----------------------------------------------------------
//
// The backend rotates refresh tokens and treats reuse of an old one as theft,
// revoking every session. A page often fires several API calls at once; if each
// noticed the expired access token and refreshed independently, the second call
// would replay an already-rotated token and log the user out.
//
// So refreshes are de-duplicated per refresh token: concurrent callers share one
// backend call, and for a few seconds afterwards late callers (whose browser has
// not yet received the new cookies) reuse its result.
//
// This state is per server process, which is correct for a single instance. A
// multi-instance deployment would need shared state (e.g. Redis) or sticky routing.

type RefreshOutcome =
  | { status: "ok"; tokens: TokenPair }
  | { status: "invalid" };

const REUSE_WINDOW_MS = 10_000;
const inflight = new Map<string, Promise<RefreshOutcome>>();
const recent = new Map<string, { outcome: RefreshOutcome; at: number }>();

async function callRefresh(refreshToken: string): Promise<RefreshOutcome> {
  const response = await fetch(`${BACKEND_URL}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
    cache: "no-store",
  });
  if (response.ok) {
    return { status: "ok", tokens: (await response.json()) as TokenPair };
  }
  if (response.status === 401) return { status: "invalid" };
  // 5xx etc: don't treat as "logged out"; let the caller surface a server error
  throw new Error(`Refresh failed with status ${response.status}`);
}

/** Drops any cached refresh result for this token (call on logout). */
export function forgetRefreshToken(refreshToken: string) {
  recent.delete(refreshToken);
}

/** Returns new tokens, or null if the refresh token is no longer valid. */
export async function refreshTokens(
  refreshToken: string,
): Promise<TokenPair | null> {
  const now = Date.now();
  for (const [key, entry] of recent) {
    if (now - entry.at > REUSE_WINDOW_MS) recent.delete(key);
  }

  const cached = recent.get(refreshToken);
  if (cached) {
    return cached.outcome.status === "ok" ? cached.outcome.tokens : null;
  }

  let pending = inflight.get(refreshToken);
  if (!pending) {
    pending = callRefresh(refreshToken)
      .then((outcome) => {
        recent.set(refreshToken, { outcome, at: Date.now() });
        return outcome;
      })
      .finally(() => inflight.delete(refreshToken));
    inflight.set(refreshToken, pending);
  }

  const outcome = await pending;
  return outcome.status === "ok" ? outcome.tokens : null;
}
