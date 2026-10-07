/**
 * Browser-side HTTP helpers. All calls go to this app's own /api routes (the BFF);
 * the browser never talks to the backend directly and never sees a token.
 */

export interface FieldError {
  field: string;
  message: string;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: FieldError[] = [],
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** Validation message for a form field, e.g. fieldError("title"). */
  fieldError(field: string): string | undefined {
    return this.details.find((d) => d.field.split(".").pop() === field)?.message;
  }
}

type QueryValue = string | number | boolean | null | undefined | string[];

function buildQuery(query?: Record<string, QueryValue>): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => params.append(key, v));
    else params.append(key, String(value));
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

async function request<T>(url: string, method: string, body?: unknown): Promise<T> {
  // FormData is sent as-is: the browser sets the multipart Content-Type (with its
  // boundary) itself, so it must not be set here.
  const isForm = body instanceof FormData;
  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: body !== undefined && !isForm ? { "Content-Type": "application/json" } : undefined,
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "Can't reach the server. Check your connection.");
  }

  if (response.status === 204) return undefined as T;

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && typeof window !== "undefined") {
      // Session is gone (the BFF already cleared the cookies). Deliberately a full
      // page load rather than router.push: this runs outside React, and a reload
      // also discards every cached query from the signed-out session.
      if (!window.location.pathname.startsWith("/login")) {
        window.location.assign(new URL("/login", window.location.origin));
      }
    }
    const error = data?.error;
    throw new ApiError(
      response.status,
      error?.code ?? "UNKNOWN_ERROR",
      error?.message ?? "Something went wrong. Please try again.",
      error?.details ?? [],
    );
  }
  return data as T;
}

/** Call the backend API through the authenticated proxy: api("workspaces/…"). */
export function api<T>(
  path: string,
  options: { method?: string; body?: unknown; query?: Record<string, QueryValue> } = {},
): Promise<T> {
  return request<T>(
    `/api/backend/${path}${buildQuery(options.query)}`,
    options.method ?? "GET",
    options.body,
  );
}

/** Upload one file as multipart form data: apiUpload("workspaces/…/documents", file). */
export function apiUpload<T>(path: string, file: File, field = "file"): Promise<T> {
  const form = new FormData();
  form.append(field, file);
  return request<T>(`/api/backend/${path}`, "POST", form);
}

/** Session endpoints (login/register/logout), which set or clear the cookies. */
export function sessionRequest<T = void>(action: "login" | "register" | "logout", body?: unknown) {
  return request<T>(`/api/session/${action}`, "POST", body ?? {});
}
