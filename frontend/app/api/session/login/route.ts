import { type NextRequest, NextResponse } from "next/server";

import {
  BACKEND_URL,
  type TokenPair,
  errorResponse,
  isSameOrigin,
  setSessionCookies,
} from "@/lib/server/session";

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) {
    return errorResponse(403, "FORBIDDEN_ORIGIN", "Cross-origin request blocked.");
  }

  let credentials: { email?: unknown; password?: unknown };
  try {
    credentials = await request.json();
  } catch {
    return errorResponse(400, "BAD_REQUEST", "Request body must be JSON.");
  }

  try {
    const upstream = await fetch(`${BACKEND_URL}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // Forward only the expected fields
      body: JSON.stringify({
        email: credentials.email,
        password: credentials.password,
      }),
      cache: "no-store",
    });

    if (!upstream.ok) {
      // Backend errors are already in the standard {error: {...}} shape
      return new NextResponse(await upstream.text(), {
        status: upstream.status,
        headers: { "Content-Type": "application/json" },
      });
    }

    const tokens = (await upstream.json()) as TokenPair;
    const response = NextResponse.json({ ok: true });
    setSessionCookies(response, tokens);
    return response;
  } catch {
    return errorResponse(502, "BACKEND_UNAVAILABLE", "The server is temporarily unavailable.");
  }
}
