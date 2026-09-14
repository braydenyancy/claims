import type {
  ClaimDetail,
  ClaimEvent,
  ClaimSummary,
  ConflictBody,
  DraftInput,
  ErrorBody,
  Meta,
  Page,
  Summary,
  User,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: unknown,
  ) {
    super(detailOf(body) ?? `HTTP ${status}`);
  }
}

export class ConflictError extends ApiError {
  constructor(public conflict: ConflictBody) {
    super(409, conflict);
  }
}

export class ValidationError extends ApiError {
  errors: Record<string, string>;

  constructor(body: ErrorBody) {
    super(400, body);
    this.errors = body.errors ?? flatten(body);
  }
}

function detailOf(body: unknown): string | undefined {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    return typeof d === "string" ? d : undefined;
  }
  return undefined;
}

// DRF's default serializer errors are {field: [messages]}; the transition
// and acknowledge routes already return {detail, errors}. Both end up as
// {field: message} for the forms.
function flatten(body: ErrorBody): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(body)) {
    if (key === "detail") continue;
    if (Array.isArray(value)) out[key] = value.map(String).join(" ");
    else if (typeof value === "string") out[key] = value;
  }
  return out;
}

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : "";
}

export async function request<T = any>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRFToken"] = csrfToken();
  const res = await fetch(path, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data: unknown = res.status === 204 ? null : await res.json().catch(() => null);
  if (res.ok) return data as T;
  if (res.status === 409) throw new ConflictError(data as ConflictBody);
  if (res.status === 400) throw new ValidationError((data ?? {}) as ErrorBody);
  throw new ApiError(res.status, data);
}

export const api = {
  login: (username: string, password: string) =>
    request<User>("POST", "/api/auth/login/", { username, password }),
  logout: () => request<void>("POST", "/api/auth/logout/"),
  me: () => request<User>("GET", "/api/me/"),
  meta: () => request<Meta>("GET", "/api/meta/"),
  claims: {
    list: (params: Record<string, string>) =>
      request<Page<ClaimSummary>>("GET", `/api/claims/?${new URLSearchParams(params)}`),
    summary: () => request<Summary>("GET", "/api/claims/summary/"),
    get: (id: number) => request<ClaimDetail>("GET", `/api/claims/${id}/`),
    create: (body: DraftInput) => request<ClaimDetail>("POST", "/api/claims/", body),
    patch: (id: number, body: Partial<DraftInput>) => request<ClaimDetail>("PATCH", `/api/claims/${id}/`, body),
    history: (id: number) => request<ClaimEvent[]>("GET", `/api/claims/${id}/history/`),
    transition: (id: number, action: string, version: number, data: Record<string, unknown>) =>
      request<ClaimDetail>("POST", `/api/claims/${id}/transition/`, { action, version, data }),
    retry: (id: number) => request<ClaimDetail>("POST", `/api/claims/${id}/registration/retry/`),
    reconcile: (id: number) => request<ClaimDetail>("POST", `/api/claims/${id}/registration/reconcile/`),
    acknowledge: (id: number, event_id: number, note: string) =>
      request<ClaimDetail>("POST", `/api/claims/${id}/acknowledge/`, { event_id, note }),
  },
};
