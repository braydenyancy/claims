# Stage 3: Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Vue 3 app that renders everything from the API's answers: login, a filtered claim list, draft creation and editing, a claim detail whose actions come from `available_actions`, inline rule errors, a conflict banner, registration and alert handling, and history.

**Architecture:** Vite dev server proxies `/api` to the Django API so the session cookie is first-party and CSRF is one header. A thin typed client maps HTTP errors to `ConflictError`, `ValidationError`, and `ApiError`. One composable holds the session; a second wraps async loads with loading, error, and 403-redirect handling. Components are generic: `ActionForm` renders inputs from the API's field schema, `StateBadge` and `RegistrationBadge` humanize whatever string they are given. The API gains a `meta` endpoint for the closed lists and two booleans (`can_edit`, `can_create_claims`) so no state or role name appears in the frontend source.

**Tech Stack:** Vue 3.5 (Composition API, `<script setup lang="ts">`), TypeScript, Vite, vue-router 4, Vitest + Vue Test Utils + jsdom. No Pinia, no component library. Backend unchanged except Task 1.

**Spec:** `docs/specs/2026-09-13-stage-3-frontend.md` (binding). Decisions D3, D4, D5, D11. Workflows W1, W2, W3, W6.

## Global Constraints

- Frontend dependencies are exactly: `vue`, `vue-router`; dev: `vite`, `@vitejs/plugin-vue`, `typescript`, `vue-tsc`, `@types/node`, `vitest`, `@vue/test-utils`, `jsdom`. Nothing else. Pin with caret ranges; commit `package-lock.json`.
- No lifecycle state name and no role name appears anywhere under `frontend/src/` except as opaque strings rendered by `StateBadge`. Registration status strings `pending`, `in_flight`, `failed` may be compared (they drive polling and the retry button and are not lifecycle rules).
- Every action the UI offers comes from `available_actions`. Blocked actions render disabled with `blocked_reason`, never hidden.
- The browser talks to `/api/...` only, same origin, through the Vite proxy. `credentials: "same-origin"`, `X-CSRFToken` from the `csrftoken` cookie on non-GET.
- Backend changes are limited to Task 1. Backend suite stays green (193 + new tests). `cd backend && uv run pytest -q` with Postgres on host port 5433.
- Frontend checks: `cd frontend && npm run typecheck && npm test` green from Task 2 on.
- Commit messages: subject + body only. No tool, model, or assistant attribution of any kind.
- Node 22 in the container (`node:22-alpine`); the machine has Node 26, which is fine for local runs.

---

### Task 1: Backend metadata and capability flags

**Files:**
- Modify: `backend/claims/api/views.py`, `backend/claims/api/urls.py`, `backend/claims/api/serializers.py`
- Modify: `backend/claims/tests/test_api.py`

**Interfaces:**
- Produces: `GET /api/meta/` → `{states: [{value, label}], denial_reasons: [{value, label}], registration_statuses: [{value, label}]}`; `UserSerializer` gains `can_create_claims: bool`; `ClaimDetailSerializer` gains `can_edit: bool` (owner and DRAFT).

- [ ] **Step 1: Write the failing tests**

Append to `backend/claims/tests/test_api.py`:

```python
@pytest.mark.django_db
def test_meta_lists_closed_lists(api, submitter):
    login(api, "sam")
    body = api.get("/api/meta/").json()
    assert [s["value"] for s in body["states"]] == list(State.values)
    assert all({"value", "label"} <= set(s) for s in body["states"])
    assert [d["value"] for d in body["denial_reasons"]] == [
        "not_covered", "duplicate", "insufficient_documentation", "out_of_network", "timely_filing",
    ]
    assert [r["value"] for r in body["registration_statuses"]] == ["pending", "in_flight", "done", "failed", "halted"]


@pytest.mark.django_db
def test_user_payload_carries_capabilities(api, submitter, reviewer):
    assert login(api, "sam")["can_create_claims"] is True
    api.post("/api/auth/logout/")
    assert login(api, "rita")["can_create_claims"] is False


@pytest.mark.django_db
def test_detail_can_edit_only_for_owner_draft(api, submitter, reviewer):
    claim = services.create_draft(created_by=submitter, payer="Acme", service_date=date(2026, 9, 1), billed_amount=Decimal("5.00"))
    login(api, "sam")
    assert api.get(f"/api/claims/{claim.id}/").json()["can_edit"] is True
    api.post(f"/api/claims/{claim.id}/transition/", {"action": "submit", "version": 0}, format="json")
    assert api.get(f"/api/claims/{claim.id}/").json()["can_edit"] is False
    api.post("/api/auth/logout/")
    login(api, "rita")
    assert api.get(f"/api/claims/{claim.id}/").json()["can_edit"] is False
```

- [ ] **Step 2: Run to verify they fail**

`cd backend && uv run pytest claims/tests/test_api.py -q`. Expected: 404 on meta, KeyError on the two flags.

- [ ] **Step 3: Implement**

In `backend/claims/api/serializers.py`:

- `UserSerializer`: add `can_create_claims = serializers.SerializerMethodField()`, include it in `fields`, and
  ```python
      def get_can_create_claims(self, user):
          return user.role == Role.SUBMITTER
  ```
  (import `Role` from `claims.models`).
- `ClaimDetailSerializer`: add `can_edit = serializers.SerializerMethodField()`, include `"can_edit"` in `fields`, and
  ```python
      def get_can_edit(self, claim):
          user = self.context["request"].user
          return claim.state == State.DRAFT and claim.created_by_id == user.id
  ```

In `backend/claims/api/views.py` add (import `DenialReason`, `RegistrationStatus`, `State` from `claims.models`):

```python
class MetaView(APIView):
    """The closed lists the UI needs for filters and labels. The UI
    renders these; it never decides anything from them (D4)."""

    def get(self, request):
        def options(choices, lower=False):
            return [{"value": v.lower() if lower else v, "label": label} for v, label in choices]

        return Response(
            {
                "states": options(State.choices),
                "denial_reasons": options(DenialReason.choices),
                "registration_statuses": options(RegistrationStatus.choices, lower=True),
            }
        )
```

In `backend/claims/api/urls.py` add `path("meta/", MetaView.as_view(), name="meta"),` after `me/`.

- [ ] **Step 4: Run the full backend suite**

`uv run pytest -q`. Expected: 196 passed, no warnings.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "Expose closed lists and capability flags for the UI

GET /api/meta/ returns the state, denial reason and registration
status lists with labels. The user payload says whether the user may
create claims and the claim detail says whether it may be edited, so
the frontend never compares a state or role name itself."
```

---

### Task 2: Frontend scaffold under compose

**Files:**
- Create: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/tsconfig.app.json`, `frontend/tsconfig.node.json`, `frontend/index.html`, `frontend/.gitignore`
- Create: `frontend/src/main.ts`, `frontend/src/App.vue`, `frontend/src/style.css`, `frontend/src/env.d.ts`, `frontend/src/api/client.ts`, `frontend/src/api/types.ts`, `frontend/src/api/client.test.ts`
- Modify: `compose.yaml`, `README.md`

**Interfaces:**
- Produces: `api/client.ts` exports `request`, `api`, `ApiError`, `ConflictError`, `ValidationError`; `api/types.ts` exports every payload type.

- [ ] **Step 1: Project files**

`frontend/package.json`:

```json
{
  "name": "claims-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc --noEmit -p tsconfig.app.json && vite build",
    "typecheck": "vue-tsc --noEmit -p tsconfig.app.json",
    "test": "vitest run"
  },
  "dependencies": {
    "vue": "^3.5.0",
    "vue-router": "^4.5.0"
  },
  "devDependencies": {
    "@types/node": "^22.0.0",
    "@vitejs/plugin-vue": "^6.0.0",
    "@vue/test-utils": "^2.4.6",
    "jsdom": "^26.0.0",
    "typescript": "~5.9.0",
    "vite": "^7.0.0",
    "vitest": "^3.2.0",
    "vue-tsc": "^3.0.0"
  }
}
```

If `npm install` rejects a range because a newer major is required for compatibility, take the nearest compatible version and note it in the report; do not add packages.

`frontend/.gitignore`:

```
node_modules/
dist/
```

`frontend/vite.config.ts`:

```ts
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vitest/config";

// The browser only ever talks to /api on its own origin. The dev server
// forwards it to the API container, so the session cookie is first-party
// and CSRF needs nothing more than the header (D3).
export default defineConfig({
  plugins: [vue()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000",
        changeOrigin: false,
      },
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts"],
  },
});
```

`frontend/tsconfig.json`:

```json
{
  "files": [],
  "references": [{ "path": "./tsconfig.app.json" }, { "path": "./tsconfig.node.json" }]
}
```

`frontend/tsconfig.app.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "isolatedModules": true,
    "verbatimModuleSyntax": true,
    "skipLibCheck": true,
    "noEmit": true,
    "jsx": "preserve",
    "types": ["vite/client", "vitest/globals"]
  },
  "include": ["src/**/*.ts", "src/**/*.vue"]
}
```

`frontend/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "skipLibCheck": true,
    "noEmit": true,
    "types": ["node"]
  },
  "include": ["vite.config.ts"]
}
```

Add `"globals": true` under `test` in `vite.config.ts` so `vitest/globals` types are honest.

`frontend/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Claims</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

`frontend/src/env.d.ts`:

```ts
/// <reference types="vite/client" />

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<Record<string, never>, Record<string, never>, unknown>;
  export default component;
}
```

`frontend/src/style.css`:

```css
:root { font-family: system-ui, sans-serif; color: #1a1a1a; background: #fafafa; }
body { margin: 0; }
main { max-width: 64rem; margin: 0 auto; padding: 1rem; }
main.narrow { max-width: 24rem; }
nav { display: flex; gap: 1rem; align-items: center; padding: 0.5rem 1rem; border-bottom: 1px solid #ddd; background: #fff; }
nav .spacer { flex: 1; }
h1 { font-size: 1.4rem; }
h2 { font-size: 1.1rem; margin-top: 1.5rem; }
label { display: block; margin: 0.5rem 0; }
input, select, textarea { font: inherit; padding: 0.3rem; width: 100%; box-sizing: border-box; }
button { font: inherit; padding: 0.4rem 0.8rem; cursor: pointer; }
button:disabled { cursor: not-allowed; opacity: 0.5; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 0.4rem; border-bottom: 1px solid #e5e5e5; vertical-align: top; }
.badge { display: inline-block; padding: 0.1rem 0.5rem; border-radius: 0.5rem; background: #e8e8e8; font-size: 0.85rem; }
.badge.final { background: #d7d7d7; }
.error { color: #b00020; }
.hint { color: #666; font-size: 0.9rem; }
.muted { color: #666; }
.banner { padding: 0.8rem; border: 1px solid #e0a800; background: #fff6d8; margin: 1rem 0; }
.alert-row { background: #fdecec; }
.warning-row { background: #fff6d8; }
.card { border: 1px solid #ddd; border-radius: 0.4rem; padding: 0.8rem; margin: 0.6rem 0; background: #fff; }
.actions { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.field-error { color: #b00020; font-size: 0.85rem; }
dl { display: grid; grid-template-columns: max-content 1fr; gap: 0.3rem 1rem; }
dt { color: #666; }
```

- [ ] **Step 2: Types**

`frontend/src/api/types.ts`:

```ts
export interface User {
  id: number;
  username: string;
  role: string;
  can_create_claims: boolean;
}

export interface Option {
  value: string;
  label: string;
}

export interface Meta {
  states: Option[];
  denial_reasons: Option[];
  registration_statuses: Option[];
}

export interface Field {
  name: string;
  type: "text" | "decimal" | "choice";
  choices: string[];
}

export interface AvailableAction {
  action: string;
  label: string;
  fields: Field[];
  blocked_reason: string | null;
}

export interface Registration {
  status: string;
  attempts?: number;
  last_error?: string;
  submission_id?: string;
  next_attempt_at?: string | null;
}

export interface ClaimSummary {
  id: number;
  reference: string;
  payer: string;
  service_date: string | null;
  billed_amount: string;
  state: string;
  version: number;
  has_open_alert: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface ClaimDetail extends ClaimSummary {
  approved_amount: string | null;
  denial_reason: string;
  submission_id: string;
  available_actions: AvailableAction[];
  registration: Registration;
  can_edit: boolean;
}

export interface ClaimEvent {
  id: number;
  action: string;
  from_state: string;
  to_state: string;
  actor: string | null;
  data: Record<string, unknown>;
  severity: "info" | "warning" | "alert";
  created_at: string;
}

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface ConflictBody {
  detail: string;
  current_state: string;
  current_version: number;
  last_event: ClaimEvent | null;
}

export interface ErrorBody {
  detail?: string;
  errors?: Record<string, string>;
  [field: string]: unknown;
}

export interface DraftInput {
  payer: string;
  service_date: string | null;
  billed_amount: string;
}
```

- [ ] **Step 3: Write the failing client test**

`frontend/src/api/client.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, ConflictError, ValidationError, request } from "./client";

function respond(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  });
}

describe("request", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("returns the body on success", async () => {
    vi.stubGlobal("fetch", respond(200, { id: 1 }));
    await expect(request("GET", "/api/x/")).resolves.toEqual({ id: 1 });
  });

  it("maps 409 to ConflictError carrying the conflict body", async () => {
    const body = { detail: "changed", current_state: "APPROVED", current_version: 3, last_event: null };
    vi.stubGlobal("fetch", respond(409, body));
    const err = await request("POST", "/api/x/", {}).catch((e) => e);
    expect(err).toBeInstanceOf(ConflictError);
    expect(err.conflict).toEqual(body);
  });

  it("maps a unified 400 to ValidationError with field errors", async () => {
    vi.stubGlobal("fetch", respond(400, { detail: "no", errors: { note: "A note is required." } }));
    const err = await request("POST", "/api/x/", {}).catch((e) => e);
    expect(err).toBeInstanceOf(ValidationError);
    expect(err.errors).toEqual({ note: "A note is required." });
  });

  it("flattens a DRF-shaped 400 into the same field errors", async () => {
    vi.stubGlobal("fetch", respond(400, { billed_amount: ["A valid number is required."], payer: ["Too long.", "Really."] }));
    const err = await request("POST", "/api/x/", {}).catch((e) => e);
    expect(err).toBeInstanceOf(ValidationError);
    expect(err.errors).toEqual({ billed_amount: "A valid number is required.", payer: "Too long. Really." });
  });

  it("maps other failures to ApiError with the status", async () => {
    vi.stubGlobal("fetch", respond(403, { detail: "Forbidden" }));
    const err = await request("GET", "/api/x/").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(403);
    expect(err.message).toBe("Forbidden");
  });

  it("sends the CSRF header on non-GET from the cookie", async () => {
    document.cookie = "csrftoken=abc123";
    const fetchMock = respond(204, null);
    vi.stubGlobal("fetch", fetchMock);
    await request("POST", "/api/x/");
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers["X-CSRFToken"]).toBe("abc123");
    expect(init.credentials).toBe("same-origin");
  });
});
```

- [ ] **Step 4: Client**

`frontend/src/api/client.ts`:

```ts
import type {
  ClaimDetail,
  ClaimEvent,
  ClaimSummary,
  ConflictBody,
  DraftInput,
  ErrorBody,
  Meta,
  Page,
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

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
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
    get: (id: number) => request<ClaimDetail>("GET", `/api/claims/${id}/`),
    create: (body: DraftInput) => request<ClaimDetail>("POST", "/api/claims/", body),
    patch: (id: number, body: Partial<DraftInput>) => request<ClaimDetail>("PATCH", `/api/claims/${id}/`, body),
    history: (id: number) => request<ClaimEvent[]>("GET", `/api/claims/${id}/history/`),
    transition: (id: number, action: string, version: number, data: Record<string, unknown>) =>
      request<ClaimDetail>("POST", `/api/claims/${id}/transition/`, { action, version, data }),
    retry: (id: number) => request<ClaimDetail>("POST", `/api/claims/${id}/registration/retry/`),
    acknowledge: (id: number, event_id: number, note: string) =>
      request<ClaimDetail>("POST", `/api/claims/${id}/acknowledge/`, { event_id, note }),
  },
};
```

- [ ] **Step 5: App shell that proves the proxy**

`frontend/src/main.ts`:

```ts
import { createApp } from "vue";
import App from "./App.vue";
import "./style.css";

createApp(App).mount("#app");
```

`frontend/src/App.vue`:

```vue
<script setup lang="ts">
import { onMounted, ref } from "vue";

const status = ref("checking…");

onMounted(async () => {
  try {
    const res = await fetch("/api/health/");
    const body = await res.json();
    status.value = `api ${body.status}, database ${body.database}`;
  } catch {
    status.value = "api unreachable";
  }
});
</script>

<template>
  <main>
    <h1>Claims</h1>
    <p>{{ status }}</p>
  </main>
</template>
```

- [ ] **Step 6: Compose and README**

Append to `compose.yaml` services:

```yaml
  frontend:
    image: node:22-alpine
    working_dir: /app
    command: sh -c "npm install && npm run dev"
    environment:
      VITE_API_PROXY_TARGET: http://api:8000
    ports:
      - "5173:5173"
    volumes:
      - ./frontend:/app
      - frontend_node_modules:/app/node_modules
    depends_on:
      api:
        condition: service_healthy
    restart: unless-stopped
```

and under top-level `volumes:` add `frontend_node_modules:`.

In `README.md` "Run": after the API line add `UI on http://localhost:5173 (the Vite dev server proxies /api to the API).` In "Develop": add `cd frontend && npm install && npm run dev` (with the API running under compose) and `npm run typecheck && npm test`. In "Layout": add `- \`frontend/\` Vue 3 app`.

- [ ] **Step 7: Verify**

`cd frontend && npm install && npm run typecheck && npm test`. Expected: typecheck clean, 6 tests passed. Then from the repo root `docker compose up --build -d`, wait for the frontend log to show the Vite URL, `curl -s localhost:5173/api/health/` → the health JSON through the proxy, then `docker compose down` and `docker compose up -d postgres`.

- [ ] **Step 8: Commit**

```bash
git add frontend compose.yaml README.md
git commit -m "Scaffold the Vue frontend behind the Vite proxy

Vite dev server proxies /api to the API container so the session
cookie stays first-party. A typed client maps 409 to ConflictError,
400 to ValidationError with flattened field errors, and everything
else to ApiError, with the CSRF header read from the cookie. Compose
serves the app on 5173 once the API is healthy."
```

---

### Task 3: Session, login, router

**Files:**
- Create: `frontend/src/composables/useSession.ts`, `frontend/src/composables/useAsync.ts`, `frontend/src/router.ts`, `frontend/src/views/LoginView.vue`, `frontend/src/views/ClaimListView.vue` (placeholder), `frontend/src/views/ClaimDetailView.vue` (placeholder)
- Modify: `frontend/src/main.ts`, `frontend/src/App.vue`

**Interfaces:**
- Produces: `useSession()` → `{ user, load, login, logout }`; `useAsync<T>()` → `{ data, error, loading, run }` with 403 → session cleared and redirect to login; routes `login`, `claims`, `claim` (`props.id: number`).

- [ ] **Step 1: Composables**

`frontend/src/composables/useSession.ts`:

```ts
import { ref } from "vue";
import { api, ApiError } from "../api/client";
import type { User } from "../api/types";

const user = ref<User | null>(null);
let loaded = false;

// One module-level session for the whole app. The server is the source
// of truth: load() asks it who we are, and a 403 means nobody.
export function useSession() {
  async function load(): Promise<User | null> {
    if (loaded) return user.value;
    try {
      user.value = await api.me();
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) user.value = null;
      else throw e;
    }
    loaded = true;
    return user.value;
  }

  async function login(username: string, password: string) {
    user.value = await api.login(username, password);
    loaded = true;
  }

  async function logout() {
    await api.logout();
    user.value = null;
  }

  function clear() {
    user.value = null;
  }

  return { user, load, login, logout, clear };
}
```

`frontend/src/composables/useAsync.ts`:

```ts
import { ref, shallowRef } from "vue";
import { useRouter } from "vue-router";
import { ApiError } from "../api/client";
import { useSession } from "./useSession";

// Loading, error, and "you are no longer signed in" handled once, so
// every view gets the same three states for free.
export function useAsync<T>() {
  const data = shallowRef<T | null>(null);
  const error = ref("");
  const loading = ref(false);
  const router = useRouter();
  const session = useSession();

  async function run(fn: () => Promise<T>): Promise<T | null> {
    loading.value = true;
    error.value = "";
    try {
      const result = await fn();
      data.value = result;
      return result;
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        session.clear();
        await router.push({ name: "login", query: { next: router.currentRoute.value.fullPath } });
        return null;
      }
      error.value = e instanceof Error ? e.message : "Something went wrong.";
      return null;
    } finally {
      loading.value = false;
    }
  }

  return { data, error, loading, run };
}
```

- [ ] **Step 2: Router and views**

`frontend/src/router.ts`:

```ts
import { createRouter, createWebHistory } from "vue-router";
import { useSession } from "./composables/useSession";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/claims" },
    { path: "/login", name: "login", component: () => import("./views/LoginView.vue") },
    { path: "/claims", name: "claims", component: () => import("./views/ClaimListView.vue") },
    {
      path: "/claims/:id",
      name: "claim",
      component: () => import("./views/ClaimDetailView.vue"),
      props: (route) => ({ id: Number(route.params.id) }),
    },
  ],
});

router.beforeEach(async (to) => {
  const session = useSession();
  const user = await session.load();
  if (to.name !== "login" && !user) return { name: "login", query: { next: to.fullPath } };
  if (to.name === "login" && user) return { name: "claims" };
});

export default router;
```

`frontend/src/views/LoginView.vue`:

```vue
<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ApiError } from "../api/client";
import { useSession } from "../composables/useSession";

const session = useSession();
const router = useRouter();
const route = useRoute();
const username = ref("");
const password = ref("");
const error = ref("");
const busy = ref(false);

async function submit() {
  error.value = "";
  busy.value = true;
  try {
    await session.login(username.value, password.value);
    await router.push(typeof route.query.next === "string" ? route.query.next : { name: "claims" });
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Could not reach the server.";
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <main class="narrow">
    <h1>Sign in</h1>
    <form @submit.prevent="submit">
      <label>Username <input v-model="username" autocomplete="username" required /></label>
      <label>Password <input v-model="password" type="password" autocomplete="current-password" required /></label>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <button :disabled="busy">Sign in</button>
    </form>
    <p class="hint">Seeded users: sam (submitter), rita and rob (reviewers). Password: password.</p>
  </main>
</template>
```

Placeholders, replaced by Tasks 4 and 5:

`frontend/src/views/ClaimListView.vue`:

```vue
<template><main><h1>Claims</h1><p class="muted">List arrives in the next cut.</p></main></template>
```

`frontend/src/views/ClaimDetailView.vue`:

```vue
<script setup lang="ts">
defineProps<{ id: number }>();
</script>
<template><main><h1>Claim {{ id }}</h1><p class="muted">Detail arrives in the next cut.</p></main></template>
```

- [ ] **Step 3: App shell**

`frontend/src/main.ts`:

```ts
import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import "./style.css";

createApp(App).use(router).mount("#app");
```

`frontend/src/App.vue`:

```vue
<script setup lang="ts">
import { useRouter } from "vue-router";
import { useSession } from "./composables/useSession";

const session = useSession();
const router = useRouter();

async function logout() {
  await session.logout();
  await router.push({ name: "login" });
}
</script>

<template>
  <nav v-if="session.user.value">
    <RouterLink :to="{ name: 'claims' }">Claims</RouterLink>
    <span class="spacer"></span>
    <span class="muted">{{ session.user.value.username }} · {{ session.user.value.role }}</span>
    <button @click="logout">Sign out</button>
  </nav>
  <RouterView />
</template>
```

Rendering `role` as text is display, not a rule; it is the one place the word appears.

- [ ] **Step 4: Verify**

`cd frontend && npm run typecheck && npm test` green. Under compose (`docker compose up -d`), open http://localhost:5173: redirected to `/login`; wrong password shows the API's message; `sam`/`password` lands on `/claims` with the nav showing `sam · submitter`; sign out returns to login; `curl -s -c /tmp/j -b /tmp/j localhost:5173/api/me/` after a browser login is not needed. Then `docker compose down && docker compose up -d postgres`.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "Add session handling, login, and routing

A module-level session composable asks the server who the user is,
the router guard redirects unauthenticated navigation to login and
back, and useAsync gives every view loading, error, and signed-out
handling from one place."
```

---

### Task 4: Claim list and draft creation

**Files:**
- Create: `frontend/src/components/StateBadge.vue`, `frontend/src/components/DraftForm.vue`, `frontend/src/lib/format.ts`
- Modify: `frontend/src/views/ClaimListView.vue`

**Interfaces:**
- Produces: `StateBadge` (`state: string`, `label?: string`), `DraftForm` (`claim?: ClaimDetail`, emits `saved(claim)`), `format.humanize(s)`, `format.money(s)`, `format.when(iso)`.

- [ ] **Step 1: Helpers and badge**

`frontend/src/lib/format.ts`:

```ts
export function humanize(value: string): string {
  return value.toLowerCase().replaceAll("_", " ");
}

export function money(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString(undefined, { style: "currency", currency: "USD" }) : value;
}

export function when(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export function ago(iso: string): string {
  const seconds = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return `${seconds} seconds ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  return `${hours} hour${hours === 1 ? "" : "s"} ago`;
}
```

`frontend/src/components/StateBadge.vue`:

```vue
<script setup lang="ts">
import { humanize } from "../lib/format";

// Renders whatever state string the API gives. It knows no state names;
// the label comes from /api/meta/ when the caller has it.
defineProps<{ state: string; label?: string }>();
</script>

<template>
  <span class="badge" :data-state="state">{{ label ?? humanize(state) }}</span>
</template>
```

- [ ] **Step 2: Draft form**

`frontend/src/components/DraftForm.vue`:

```vue
<script setup lang="ts">
import { reactive, ref } from "vue";
import { api, ValidationError } from "../api/client";
import type { ClaimDetail } from "../api/types";

const props = defineProps<{ claim?: ClaimDetail }>();
const emit = defineEmits<{ saved: [claim: ClaimDetail] }>();

const form = reactive({
  payer: props.claim?.payer ?? "",
  service_date: props.claim?.service_date ?? "",
  billed_amount: props.claim?.billed_amount ?? "",
});
const errors = ref<Record<string, string>>({});
const failure = ref("");
const busy = ref(false);

async function submit() {
  errors.value = {};
  failure.value = "";
  busy.value = true;
  const body = {
    payer: form.payer,
    service_date: form.service_date || null,
    billed_amount: form.billed_amount,
  };
  try {
    const saved = props.claim ? await api.claims.patch(props.claim.id, body) : await api.claims.create(body);
    emit("saved", saved);
  } catch (e) {
    if (e instanceof ValidationError) errors.value = e.errors;
    else failure.value = e instanceof Error ? e.message : "Could not save.";
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <form class="card" @submit.prevent="submit">
    <h2>{{ claim ? "Edit draft" : "New draft" }}</h2>
    <label>
      Payer
      <input v-model="form.payer" />
      <span v-if="errors.payer" class="field-error">{{ errors.payer }}</span>
    </label>
    <label>
      Service date
      <input v-model="form.service_date" type="date" />
      <span v-if="errors.service_date" class="field-error">{{ errors.service_date }}</span>
    </label>
    <label>
      Billed amount
      <input v-model="form.billed_amount" inputmode="decimal" required />
      <span v-if="errors.billed_amount" class="field-error">{{ errors.billed_amount }}</span>
    </label>
    <p v-if="failure" class="error" role="alert">{{ failure }}</p>
    <button :disabled="busy">{{ claim ? "Save" : "Create draft" }}</button>
  </form>
</template>
```

- [ ] **Step 3: List view**

Replace `frontend/src/views/ClaimListView.vue`:

```vue
<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api/client";
import type { ClaimDetail, ClaimSummary, Meta, Page } from "../api/types";
import DraftForm from "../components/DraftForm.vue";
import StateBadge from "../components/StateBadge.vue";
import { useAsync } from "../composables/useAsync";
import { useSession } from "../composables/useSession";
import { money, when } from "../lib/format";

const router = useRouter();
const session = useSession();
const meta = ref<Meta | null>(null);
const state = ref("");
const openAlerts = ref(false);
const showDraft = ref(false);
const page = useAsync<Page<ClaimSummary>>();

function labelFor(value: string) {
  return meta.value?.states.find((s) => s.value === value)?.label;
}

async function load() {
  const params: Record<string, string> = {};
  if (state.value) params.state = state.value;
  if (openAlerts.value) params.alert = "open";
  await page.run(() => api.claims.list(params));
}

async function created(claim: ClaimDetail) {
  showDraft.value = false;
  await router.push({ name: "claim", params: { id: claim.id } });
}

onMounted(async () => {
  meta.value = await api.meta().catch(() => null);
  await load();
});
watch([state, openAlerts], load);
</script>

<template>
  <main>
    <h1>Claims</h1>

    <section class="filters actions">
      <label>
        State
        <select v-model="state">
          <option value="">all</option>
          <option v-for="s in meta?.states ?? []" :key="s.value" :value="s.value">{{ s.label }}</option>
        </select>
      </label>
      <label><input v-model="openAlerts" type="checkbox" /> open alerts only</label>
      <button v-if="session.user.value?.can_create_claims" @click="showDraft = !showDraft">
        {{ showDraft ? "Cancel" : "New draft" }}
      </button>
    </section>

    <DraftForm v-if="showDraft" @saved="created" />

    <p v-if="page.loading.value" class="muted">Loading claims…</p>
    <p v-else-if="page.error.value" class="error" role="alert">
      {{ page.error.value }} <button @click="load">Retry</button>
    </p>
    <p v-else-if="page.data.value && page.data.value.results.length === 0" class="muted">No claims match.</p>
    <table v-else-if="page.data.value">
      <thead>
        <tr><th>Reference</th><th>Payer</th><th>State</th><th>Billed</th><th>Updated</th><th></th></tr>
      </thead>
      <tbody>
        <tr v-for="c in page.data.value.results" :key="c.id">
          <td><RouterLink :to="{ name: 'claim', params: { id: c.id } }">{{ c.reference }}</RouterLink></td>
          <td>{{ c.payer || "—" }}</td>
          <td><StateBadge :state="c.state" :label="labelFor(c.state)" /></td>
          <td>{{ money(c.billed_amount) }}</td>
          <td>{{ when(c.updated_at) }}</td>
          <td><span v-if="c.has_open_alert" class="badge alert-row">alert</span></td>
        </tr>
      </tbody>
    </table>
    <p v-if="page.data.value && page.data.value.count > page.data.value.results.length" class="hint">
      Showing {{ page.data.value.results.length }} of {{ page.data.value.count }}.
    </p>
  </main>
</template>
```

- [ ] **Step 4: Verify**

Typecheck and tests green. Under compose as `sam`: the list shows sam's seeded claims with badges; the state filter narrows; "New draft" creates a claim and lands on its detail placeholder; an invalid billed amount shows the field error inline. As `rita`: all claims; "open alerts only" shows the seeded failed claim. Then compose down, postgres up.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "Add the claim list with filters and draft creation

State labels come from the meta endpoint; the badge renders whatever
string it is given. Filters are query params the API interprets. The
draft form shows only when the user payload says the user may create
claims, and shows the API's field errors inline."
```

---

### Task 5: Claim detail, read side

**Files:**
- Create: `frontend/src/components/RegistrationBadge.vue`, `frontend/src/components/HistoryTable.vue`
- Modify: `frontend/src/views/ClaimDetailView.vue`

**Interfaces:**
- Produces: `RegistrationBadge` (`registration: Registration`, `labels?: Option[]`), `HistoryTable` (`events: ClaimEvent[]`); the detail view exposes `reload()` used by later cuts.

- [ ] **Step 1: Components**

`frontend/src/components/RegistrationBadge.vue`:

```vue
<script setup lang="ts">
import type { Option, Registration } from "../api/types";
import { humanize, when } from "../lib/format";

const props = defineProps<{ registration: Registration; labels?: Option[] }>();

function label() {
  return props.labels?.find((o) => o.value === props.registration.status)?.label ?? humanize(props.registration.status);
}
</script>

<template>
  <span class="badge" :data-registration="registration.status">registration: {{ label() }}</span>
  <span v-if="registration.submission_id" class="muted"> · {{ registration.submission_id }}</span>
  <span v-if="registration.attempts" class="muted"> · attempts {{ registration.attempts }}</span>
  <span v-if="registration.next_attempt_at" class="muted"> · next try {{ when(registration.next_attempt_at) }}</span>
  <span v-if="registration.last_error" class="error"> · {{ registration.last_error }}</span>
</template>
```

`frontend/src/components/HistoryTable.vue`:

```vue
<script setup lang="ts">
import type { ClaimEvent } from "../api/types";
import { humanize, when } from "../lib/format";

defineProps<{ events: ClaimEvent[] }>();

function summary(data: Record<string, unknown>): string {
  return Object.entries(data)
    .map(([k, v]) => `${humanize(k)}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
    .join(" · ");
}
</script>

<template>
  <p v-if="events.length === 0" class="muted">No history yet.</p>
  <table v-else>
    <thead>
      <tr><th>When</th><th>Who</th><th>What</th><th>State</th><th>Details</th></tr>
    </thead>
    <tbody>
      <tr v-for="e in events" :key="e.id" :class="{ 'alert-row': e.severity === 'alert', 'warning-row': e.severity === 'warning' }">
        <td>{{ when(e.created_at) }}</td>
        <td>{{ e.actor ?? "system" }}</td>
        <td>{{ humanize(e.action) }}<span v-if="e.severity !== 'info'" class="hint"> ({{ e.severity }})</span></td>
        <td>
          <span v-if="e.from_state !== e.to_state">{{ humanize(e.from_state) }} → {{ humanize(e.to_state) }}</span>
          <span v-else class="muted">{{ humanize(e.to_state) }}</span>
        </td>
        <td class="hint">{{ summary(e.data) }}</td>
      </tr>
    </tbody>
  </table>
</template>
```

- [ ] **Step 2: Detail view, read side**

Replace `frontend/src/views/ClaimDetailView.vue`:

```vue
<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api } from "../api/client";
import type { ClaimDetail, ClaimEvent, Meta } from "../api/types";
import HistoryTable from "../components/HistoryTable.vue";
import RegistrationBadge from "../components/RegistrationBadge.vue";
import StateBadge from "../components/StateBadge.vue";
import { useAsync } from "../composables/useAsync";
import { money, when } from "../lib/format";

const props = defineProps<{ id: number }>();

const meta = ref<Meta | null>(null);
const claim = useAsync<ClaimDetail>();
const history = ref<ClaimEvent[]>([]);

function stateLabel(value: string) {
  return meta.value?.states.find((s) => s.value === value)?.label;
}

async function reload() {
  const [c, h] = await Promise.all([claim.run(() => api.claims.get(props.id)), api.claims.history(props.id).catch(() => [])]);
  if (c) history.value = h;
}

onMounted(async () => {
  meta.value = await api.meta().catch(() => null);
  await reload();
});
</script>

<template>
  <main>
    <p><RouterLink :to="{ name: 'claims' }">← Claims</RouterLink></p>

    <p v-if="claim.loading.value && !claim.data.value" class="muted">Loading claim…</p>
    <p v-else-if="claim.error.value" class="error" role="alert">{{ claim.error.value }} <button @click="reload">Retry</button></p>

    <template v-else-if="claim.data.value">
      <h1>
        {{ claim.data.value.reference }}
        <StateBadge :state="claim.data.value.state" :label="stateLabel(claim.data.value.state)" />
      </h1>
      <p><RegistrationBadge :registration="claim.data.value.registration" :labels="meta?.registration_statuses" /></p>

      <section class="card">
        <dl>
          <dt>Payer</dt><dd>{{ claim.data.value.payer || "—" }}</dd>
          <dt>Service date</dt><dd>{{ claim.data.value.service_date ?? "—" }}</dd>
          <dt>Billed</dt><dd>{{ money(claim.data.value.billed_amount) }}</dd>
          <dt>Approved</dt><dd>{{ money(claim.data.value.approved_amount) }}</dd>
          <dt v-if="claim.data.value.denial_reason">Denial reason</dt><dd v-if="claim.data.value.denial_reason">{{ claim.data.value.denial_reason }}</dd>
          <dt>Created by</dt><dd>{{ claim.data.value.created_by }} · {{ when(claim.data.value.created_at) }}</dd>
          <dt>Version</dt><dd>{{ claim.data.value.version }}</dd>
        </dl>
      </section>

      <h2>History</h2>
      <HistoryTable :events="history" />
    </template>
  </main>
</template>
```

- [ ] **Step 3: Verify**

Typecheck and tests green. Under compose: a seeded approved claim shows both badges, fields, and a history with system rows labelled "system" and the alert row highlighted on the failed seed claim. Then compose down, postgres up.

- [ ] **Step 4: Commit**

```bash
git add frontend
git commit -m "Add the claim detail read side

State and registration badges, the claim's fields, and the history
table with severity highlighting and system events shown as such.
Labels come from the meta endpoint; nothing in the view knows a state
name."
```

---

### Task 6: Claim detail, write side

**Files:**
- Create: `frontend/src/components/ActionForm.vue`, `frontend/src/components/ActionPanel.vue`, `frontend/src/components/ConflictBanner.vue`, `frontend/src/components/ActionForm.test.ts`
- Modify: `frontend/src/views/ClaimDetailView.vue`

**Interfaces:**
- Produces: `ActionForm` (`action: AvailableAction`, `choiceLabels?: Option[]`, `errors: Record<string,string>`, `busy: boolean`; emits `submit(data)`, `cancel`); `ActionPanel` (`actions`, `disabled`, `choiceLabels?`, `errors`, `busy`, `active: string | null`; emits `run(action, data)`, `open(action)`, `close`); `ConflictBanner` (`conflict: ConflictBody`; emits `reload`).

- [ ] **Step 1: Write the failing ActionForm test**

`frontend/src/components/ActionForm.test.ts`:

```ts
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ActionForm from "./ActionForm.vue";

const base = { action: "x", label: "X", blocked_reason: null };

describe("ActionForm", () => {
  it("renders a textarea for a text field and submits its value", async () => {
    const w = mount(ActionForm, {
      props: { action: { ...base, fields: [{ name: "note", type: "text", choices: [] }] }, errors: {}, busy: false },
    });
    await w.find("textarea").setValue("Please attach the report.");
    await w.find("form").trigger("submit");
    expect(w.emitted("submit")?.[0]).toEqual([{ note: "Please attach the report." }]);
  });

  it("renders a select with the declared choices and their labels", () => {
    const w = mount(ActionForm, {
      props: {
        action: { ...base, fields: [{ name: "denial_reason", type: "choice", choices: ["duplicate", "not_covered"] }] },
        choiceLabels: [{ value: "duplicate", label: "Duplicate claim" }],
        errors: {},
        busy: false,
      },
    });
    const options = w.findAll("option").map((o) => [o.attributes("value"), o.text()]);
    expect(options).toEqual([
      ["duplicate", "Duplicate claim"],
      ["not_covered", "not covered"],
    ]);
  });

  it("renders a decimal input and shows the field error it is given", () => {
    const w = mount(ActionForm, {
      props: {
        action: { ...base, fields: [{ name: "approved_amount", type: "decimal", choices: [] }] },
        errors: { approved_amount: "Approved amount cannot exceed the billed amount." },
        busy: false,
      },
    });
    expect(w.find("input[inputmode=decimal]").exists()).toBe(true);
    expect(w.text()).toContain("cannot exceed");
  });
});
```

- [ ] **Step 2: Components**

`frontend/src/components/ActionForm.vue`:

```vue
<script setup lang="ts">
import { reactive } from "vue";
import type { AvailableAction, Option } from "../api/types";
import { humanize } from "../lib/format";

// Generic on purpose: it renders whatever fields the API declares for
// the action, so a new transition on the server needs no change here.
const props = defineProps<{
  action: AvailableAction;
  choiceLabels?: Option[];
  errors: Record<string, string>;
  busy: boolean;
}>();
const emit = defineEmits<{ submit: [data: Record<string, string>]; cancel: [] }>();

const values = reactive<Record<string, string>>(Object.fromEntries(props.action.fields.map((f) => [f.name, ""])));

function labelFor(choice: string) {
  return props.choiceLabels?.find((o) => o.value === choice)?.label ?? humanize(choice);
}
</script>

<template>
  <form class="card" @submit.prevent="emit('submit', { ...values })">
    <h2>{{ action.label }}</h2>
    <label v-for="f in action.fields" :key="f.name">
      {{ humanize(f.name) }}
      <textarea v-if="f.type === 'text'" v-model="values[f.name]" rows="3"></textarea>
      <select v-else-if="f.type === 'choice'" v-model="values[f.name]">
        <option v-for="c in f.choices" :key="c" :value="c">{{ labelFor(c) }}</option>
      </select>
      <input v-else v-model="values[f.name]" inputmode="decimal" />
      <span v-if="errors[f.name]" class="field-error">{{ errors[f.name] }}</span>
    </label>
    <p v-if="errors.detail" class="error">{{ errors.detail }}</p>
    <div class="actions">
      <button :disabled="busy">{{ action.label }}</button>
      <button type="button" :disabled="busy" @click="emit('cancel')">Cancel</button>
    </div>
  </form>
</template>
```

`frontend/src/components/ActionPanel.vue`:

```vue
<script setup lang="ts">
import type { AvailableAction, Option } from "../api/types";
import ActionForm from "./ActionForm.vue";

// Buttons come from the API's list and nothing else. A blocked action is
// shown disabled with its reason (spec: never hidden).
const props = defineProps<{
  actions: AvailableAction[];
  disabled: boolean;
  choiceLabels?: Option[];
  errors: Record<string, string>;
  busy: boolean;
  active: string | null;
}>();
const emit = defineEmits<{ run: [action: string, data: Record<string, string>]; open: [action: string]; close: [] }>();

function click(a: AvailableAction) {
  if (a.fields.length === 0) emit("run", a.action, {});
  else emit("open", a.action);
}

function activeAction() {
  return props.actions.find((a) => a.action === props.active) ?? null;
}
</script>

<template>
  <section>
    <h2>Actions</h2>
    <p v-if="actions.length === 0" class="muted">No actions available to you right now.</p>
    <div v-else class="actions">
      <span v-for="a in actions" :key="a.action">
        <button :disabled="disabled || busy || a.blocked_reason !== null" :title="a.blocked_reason ?? ''" @click="click(a)">
          {{ a.label }}
        </button>
        <span v-if="a.blocked_reason" class="hint"> {{ a.blocked_reason }}</span>
      </span>
    </div>
    <ActionForm
      v-if="activeAction()"
      :key="active ?? ''"
      :action="activeAction()!"
      :choice-labels="choiceLabels"
      :errors="errors"
      :busy="busy"
      @submit="(data) => emit('run', active!, data)"
      @cancel="emit('close')"
    />
  </section>
</template>
```

`frontend/src/components/ConflictBanner.vue`:

```vue
<script setup lang="ts">
import type { ConflictBody } from "../api/types";
import { ago, humanize } from "../lib/format";

defineProps<{ conflict: ConflictBody }>();
defineEmits<{ reload: [] }>();
</script>

<template>
  <div class="banner" role="alert">
    <strong>This claim changed while you were looking at it.</strong>
    <p v-if="conflict.last_event">
      {{ conflict.last_event.actor ?? "The system" }} {{ humanize(conflict.last_event.action) }}
      {{ ago(conflict.last_event.created_at) }}. It is now {{ humanize(conflict.current_state) }}.
    </p>
    <p v-else>It is now {{ humanize(conflict.current_state) }}.</p>
    <button @click="$emit('reload')">Reload</button>
  </div>
</template>
```

- [ ] **Step 3: Wire into the detail view**

In `frontend/src/views/ClaimDetailView.vue`, add imports for `ConflictError`, `ValidationError` from the client, `ActionPanel`, `ConflictBanner`, `DraftForm`, and `ConflictBody`; add state and handlers:

```ts
const conflict = ref<ConflictBody | null>(null);
const active = ref<string | null>(null);
const actionErrors = ref<Record<string, string>>({});
const actionBusy = ref(false);
const editing = ref(false);

async function runAction(action: string, data: Record<string, string>) {
  const current = claim.data.value;
  if (!current) return;
  actionErrors.value = {};
  actionBusy.value = true;
  try {
    claim.data.value = await api.claims.transition(current.id, action, current.version, data);
    active.value = null;
    history.value = await api.claims.history(current.id).catch(() => history.value);
  } catch (e) {
    if (e instanceof ConflictError) conflict.value = e.conflict;
    else if (e instanceof ValidationError) actionErrors.value = e.errors;
    else actionErrors.value = { detail: e instanceof Error ? e.message : "Could not perform the action." };
  } finally {
    actionBusy.value = false;
  }
}

async function afterConflict() {
  conflict.value = null;
  active.value = null;
  actionErrors.value = {};
  await reload();
}

async function saved(updated: ClaimDetail) {
  claim.data.value = updated;
  editing.value = false;
  history.value = await api.claims.history(updated.id).catch(() => history.value);
}
```

In the template, after the registration badge line and before the fields card:

```vue
      <ConflictBanner v-if="conflict" :conflict="conflict" @reload="afterConflict" />

      <ActionPanel
        :actions="claim.data.value.available_actions"
        :disabled="conflict !== null"
        :choice-labels="meta?.denial_reasons"
        :errors="actionErrors"
        :busy="actionBusy"
        :active="active"
        @run="runAction"
        @open="(a) => { active = a; actionErrors = {}; }"
        @close="active = null"
      />

      <p v-if="claim.data.value.can_edit && !editing"><button @click="editing = true">Edit draft</button></p>
      <DraftForm v-if="editing" :claim="claim.data.value" @saved="saved" />
```

`choice-labels` passes the denial reasons for the deny form; a choice field for any other list would fall back to humanized values.

- [ ] **Step 4: Verify**

`npm run typecheck && npm test` green (9 tests). Under compose: as `sam`, a draft with no payer shows Submit disabled with the reason and Withdraw enabled; edit the draft to add payer and date, Submit works and the badge shows pending. As `rita`, on an under-review claim, Approve with an amount above billed shows the inline error and keeps the form; a valid amount approves. Two reviewer windows on one claim: the second action shows the conflict banner naming who did what; Reload clears it. Then compose down, postgres up.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "Add the claim detail write side

Action buttons and forms render from available_actions, blocked ones
disabled with their reason. A stale version shows a conflict banner
built from the 409 body and disables the panel until reload. Rule
failures show inline and keep the form open. Drafts the user may edit
get the draft form."
```

---

### Task 7: Alerts, retry, polling

**Files:**
- Create: `frontend/src/components/AlertPanel.vue`
- Modify: `frontend/src/views/ClaimDetailView.vue`

**Interfaces:**
- Produces: `AlertPanel` (`events: ClaimEvent[]`, `claimId: number`, `canAct: boolean`; emits `updated(claim)`).

- [ ] **Step 1: Alert panel**

`frontend/src/components/AlertPanel.vue`:

```vue
<script setup lang="ts">
import { computed, ref } from "vue";
import { api, ValidationError } from "../api/client";
import type { ClaimDetail, ClaimEvent } from "../api/types";
import { humanize, when } from "../lib/format";

const props = defineProps<{ events: ClaimEvent[]; claimId: number; canAct: boolean }>();
const emit = defineEmits<{ updated: [claim: ClaimDetail] }>();

const notes = ref<Record<number, string>>({});
const errors = ref<Record<number, string>>({});
const busy = ref<number | null>(null);

// An alert is open until an alert_acknowledged event names its id.
const alerts = computed(() => {
  const acks = new Map<number, ClaimEvent>();
  for (const e of props.events) {
    if (e.action === "alert_acknowledged" && typeof e.data.event_id === "number") acks.set(e.data.event_id, e);
  }
  return props.events.filter((e) => e.severity === "alert").map((e) => ({ event: e, ack: acks.get(e.id) ?? null }));
});

async function acknowledge(eventId: number) {
  errors.value = { ...errors.value, [eventId]: "" };
  busy.value = eventId;
  try {
    const claim = await api.claims.acknowledge(props.claimId, eventId, notes.value[eventId] ?? "");
    notes.value = { ...notes.value, [eventId]: "" };
    emit("updated", claim);
  } catch (e) {
    const msg = e instanceof ValidationError ? Object.values(e.errors).join(" ") : e instanceof Error ? e.message : "Failed.";
    errors.value = { ...errors.value, [eventId]: msg };
  } finally {
    busy.value = null;
  }
}
</script>

<template>
  <section v-if="alerts.length">
    <h2>Alerts</h2>
    <div v-for="{ event, ack } in alerts" :key="event.id" class="card" :class="{ 'alert-row': !ack }">
      <p><strong>{{ humanize(event.action) }}</strong> · {{ when(event.created_at) }}</p>
      <p class="hint">{{ JSON.stringify(event.data) }}</p>
      <p v-if="ack">Acknowledged by {{ ack.actor }} {{ when(ack.created_at) }}: “{{ ack.data.note }}”</p>
      <form v-else-if="canAct" @submit.prevent="acknowledge(event.id)">
        <label>Note <textarea v-model="notes[event.id]" rows="2" required></textarea></label>
        <p v-if="errors[event.id]" class="field-error">{{ errors[event.id] }}</p>
        <button :disabled="busy === event.id">Acknowledge</button>
      </form>
      <p v-else class="muted">Open. A reviewer will acknowledge it.</p>
    </div>
  </section>
</template>
```

`canAct` is whether the acknowledge form is offered; the server still decides. Pass `claim.available_actions` presence is not a proxy for reviewer-ness, so the view passes `true` and lets a 403 surface as the error text. Simplest honest choice: pass `canAct: true` always; a submitter who tries gets the API's message.

- [ ] **Step 2: Retry and polling in the detail view**

In `ClaimDetailView.vue` add:

```ts
import { onBeforeUnmount, watch } from "vue";
import AlertPanel from "../components/AlertPanel.vue";

const retryBusy = ref(false);
const retryError = ref("");
let timer: ReturnType<typeof setInterval> | null = null;

async function retry() {
  const current = claim.data.value;
  if (!current) return;
  retryBusy.value = true;
  retryError.value = "";
  try {
    claim.data.value = await api.claims.retry(current.id);
    history.value = await api.claims.history(current.id).catch(() => history.value);
  } catch (e) {
    retryError.value = e instanceof Error ? e.message : "Could not retry.";
  } finally {
    retryBusy.value = false;
  }
}

function polling(status: string | undefined) {
  const wants = status === "pending" || status === "in_flight";
  if (wants && timer === null) timer = setInterval(reload, 3000);
  if (!wants && timer !== null) {
    clearInterval(timer);
    timer = null;
  }
}

watch(() => claim.data.value?.registration.status, polling, { immediate: true });
onBeforeUnmount(() => polling(undefined));
```

`reload` must not flash the loading state while polling; it already only shows "Loading claim…" when there is no data.

In the template, after the registration badge paragraph:

```vue
      <p v-if="claim.data.value.registration.status === 'failed'">
        <button :disabled="retryBusy" @click="retry">Retry registration</button>
        <span v-if="retryError" class="error"> {{ retryError }}</span>
      </p>

      <AlertPanel :events="history" :claim-id="claim.data.value.id" :can-act="true" @updated="saved" />
```

- [ ] **Step 3: Verify**

Typecheck and tests green. Under compose: as `sam`, submit a draft and watch the badge go pending then done without reloading. As `rita`, the seeded failed claim shows Retry; after it the badge reaches done and the alert card remains open; acknowledging with a blank note shows the error; with a note, the card shows the acknowledgement and the list's alert marker clears. Then compose down, postgres up.

- [ ] **Step 4: Commit**

```bash
git add frontend
git commit -m "Add alerts, registration retry, and polling

Alerts are derived from history: an alert event is open until an
acknowledgement names it. Acknowledging requires a note and shows the
API's error otherwise. A failed registration offers retry. While a
registration is pending or in flight the detail polls every three
seconds and stops when it settles."
```

---

### Task 8: Close stage 3

**Files:**
- Create: `docs/receipts/stage-3/README.md` and screenshots under `docs/receipts/stage-3/`
- Modify: `NOTES.md`, `docs/specs/2026-09-13-stage-3-frontend.md`, `README.md`

- [ ] **Step 1: Receipts with screenshots**

Bring the stack up clean (`docker compose down -v && docker compose up --build -d`). Use the browser tools available to you (`agent_browser_open`, `agent_browser_snapshot`, `agent_browser_click`, `agent_browser_fill`, `agent_browser_screenshot`, and the rest) to walk the done criteria at http://localhost:5173, saving a PNG for each into `docs/receipts/stage-3/`:

1. `01-login.png` login page; `02-list-sam.png` sam's list.
2. `03-blocked-submit.png` a new draft with no payer showing Submit disabled with its reason.
3. `04-pending-badge.png` after editing and submitting: registration pending; `05-done-badge.png` after polling reaches done.
4. `06-rule-error.png` rita approving above billed: inline error, form open.
5. `07-conflict.png` two tabs as rita and rob on one under-review claim, the second action showing the conflict banner naming the other reviewer.
6. `08-retry-and-alert.png` the seeded failed claim after Retry with the alert card; `09-acknowledged.png` after acknowledging with a note.
7. `10-empty.png` a filter with no matches.

If the browser tools cannot save a PNG to a path, save what they return (base64) to the file with a shell command. If no browser tool works at all, write the receipts as a curl walk against the proxy (`localhost:5173/api/...`) proving the UI-facing responses, state clearly that screenshots could not be captured, and stop there rather than fabricating.

`docs/receipts/stage-3/README.md` lists each screenshot with one line saying what it shows and the command or click path that produced it, plus the pasted output of `npm run typecheck`, `npm test`, and the grep from the spec's done criteria:

```
grep -rnE "DRAFT|SUBMITTED|UNDER_REVIEW|INFO_REQUESTED|APPROVED|DENIED|WITHDRAWN|submitter|reviewer" frontend/src
```

which must return nothing except the `App.vue` line that displays `role` as text. Paste the actual output.

Then `docker compose down && docker compose up -d postgres`.

- [ ] **Step 2: NOTES.md**

Append `## Stage 3: frontend`, about 200 words: the proxy decision and why CORS never came up; the client's three error classes; that every action and its form come from `available_actions` and the field schema, with blocked actions shown disabled; that `meta`, `can_edit`, and `can_create_claims` exist so no state or role name lives in the frontend, and the grep that proves it; the conflict banner built from the 409 body; polling while registration is pending; what is deferred (production build and static serving, pagination controls, real-time push, a11y pass, the deferred backend hygiene list from stages 1 and 2); AI use consistent with earlier sections.

- [ ] **Step 3: Spec and README**

Spec: `Status: complete.`, all cuts `- [x]`. README: confirm the run instructions match (one command, two URLs, seeded logins).

- [ ] **Step 4: Commit**

```bash
git add NOTES.md docs README.md
git commit -m "Close stage 3: receipts, notes, spec status

Screenshots of the done criteria under compose, the grep proving no
lifecycle or role rule lives in the frontend, the stage 3 notes, and
the spec ticked."
```
