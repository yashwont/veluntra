import { type NextRequest, NextResponse } from "next/server";

import {
  ACCESS_COOKIE,
  BACKEND_URL,
  REFRESH_COOKIE,
  type TokenPair,
  errorResponse,
  isSameOrigin,
  refreshTokens,
  setSessionCookies,
  unauthenticatedResponse,
} from "@/lib/server/session";

/**
 * Authenticated proxy to the backend API: /api/backend/<path> -> {BACKEND}/api/v1/<path>.
 *
 * The browser sends only its httpOnly cookies; this handler attaches the access
 * token, refreshes it when needed, and forwards the request.
 */

// Only these API areas are reachable from the browser. Auth endpoints are
// deliberately excluded: they're handled by /api/session/* so tokens never
// reach client code.
const ALLOWED_ROOTS = new Set(["users", "workspaces"]);
const SAFE_SEGMENT = /^[A-Za-z0-9_-]+$/;

type Context = RouteContext<"/api/backend/[...path]">;

async function forward(
  url: string,
  method: string,
  body: string | undefined,
  accessToken: string,
): Promise<Response> {
  return fetch(url, {
    method,
    headers: {
      Authorization: `Bearer ${accessToken}`,
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body,
    cache: "no-store",
  });
}

async function handle(request: NextRequest, context: Context) {
  const method = request.method;
  const isRead = method === "GET" || method === "HEAD";
  if (!isRead && !isSameOrigin(request)) {
    return errorResponse(403, "FORBIDDEN_ORIGIN", "Cross-origin request blocked.");
  }

  const { path } = await context.params;
  if (!ALLOWED_ROOTS.has(path[0]) || !path.every((s) => SAFE_SEGMENT.test(s))) {
    return errorResponse(404, "NOT_FOUND", "The requested resource does not exist.");
  }

  const url = `${BACKEND_URL}/api/v1/${path.join("/")}${request.nextUrl.search}`;
  const body = isRead ? undefined : await request.text();

  let accessToken = request.cookies.get(ACCESS_COOKIE)?.value;
  const refreshToken = request.cookies.get(REFRESH_COOKIE)?.value;
  let renewed: TokenPair | null = null;

  try {
    // Access cookie expired (the browser dropped it): renew before calling
    if (!accessToken && refreshToken) {
      renewed = await refreshTokens(refreshToken);
      accessToken = renewed?.access_token;
    }
    if (!accessToken) return unauthenticatedResponse();

    let upstream = await forward(url, method, body, accessToken);

    // Token rejected despite being present (e.g. revoked): try one renewal
    if (upstream.status === 401 && refreshToken && !renewed) {
      renewed = await refreshTokens(refreshToken);
      if (!renewed) return unauthenticatedResponse();
      upstream = await forward(url, method, body, renewed.access_token);
    }

    const response = new NextResponse(
      upstream.status === 204 ? null : await upstream.text(),
      {
        status: upstream.status,
        headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
      },
    );
    if (renewed) setSessionCookies(response, renewed);
    return response;
  } catch {
    return errorResponse(502, "BACKEND_UNAVAILABLE", "The server is temporarily unavailable.");
  }
}

export {
  handle as GET,
  handle as POST,
  handle as PATCH,
  handle as PUT,
  handle as DELETE,
};
