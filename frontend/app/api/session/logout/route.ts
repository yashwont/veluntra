import { type NextRequest, NextResponse } from "next/server";

import {
  BACKEND_URL,
  REFRESH_COOKIE,
  clearSessionCookies,
  errorResponse,
  forgetRefreshToken,
  isSameOrigin,
} from "@/lib/server/session";

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) {
    return errorResponse(403, "FORBIDDEN_ORIGIN", "Cross-origin request blocked.");
  }

  const refreshToken = request.cookies.get(REFRESH_COOKIE)?.value;
  if (refreshToken) {
    forgetRefreshToken(refreshToken);
    try {
      // Revoke server-side so the token is useless even if it was copied
      await fetch(`${BACKEND_URL}/api/v1/auth/logout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
        cache: "no-store",
      });
    } catch {
      // Best effort: the cookies are cleared below regardless
    }
  }

  const response = NextResponse.json({ ok: true });
  clearSessionCookies(response);
  return response;
}
