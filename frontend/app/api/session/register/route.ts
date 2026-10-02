import { type NextRequest, NextResponse } from "next/server";

import {
  BACKEND_URL,
  type TokenPair,
  errorResponse,
  isSameOrigin,
  setSessionCookies,
} from "@/lib/server/session";

async function backendPost(path: string, payload: unknown): Promise<Response> {
  return fetch(`${BACKEND_URL}/api/v1/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
}

/** Creates the account, then signs the user in so they land straight in the app. */
export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) {
    return errorResponse(403, "FORBIDDEN_ORIGIN", "Cross-origin request blocked.");
  }

  let input: { email?: unknown; password?: unknown; full_name?: unknown };
  try {
    input = await request.json();
  } catch {
    return errorResponse(400, "BAD_REQUEST", "Request body must be JSON.");
  }

  try {
    const registered = await backendPost("auth/register", {
      email: input.email,
      password: input.password,
      full_name: input.full_name,
    });
    if (!registered.ok) {
      return new NextResponse(await registered.text(), {
        status: registered.status,
        headers: { "Content-Type": "application/json" },
      });
    }

    const login = await backendPost("auth/login", {
      email: input.email,
      password: input.password,
    });
    if (!login.ok) {
      // Account exists but auto-login failed: send the user to the login page
      return errorResponse(
        500,
        "LOGIN_AFTER_REGISTER_FAILED",
        "Your account was created, but signing in failed. Please log in.",
      );
    }

    const response = NextResponse.json({ ok: true }, { status: 201 });
    setSessionCookies(response, (await login.json()) as TokenPair);
    return response;
  } catch {
    return errorResponse(502, "BACKEND_UNAVAILABLE", "The server is temporarily unavailable.");
  }
}
