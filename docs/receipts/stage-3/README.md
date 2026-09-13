# Stage 3 receipts

Recorded 2026-09-13 on branch `stage-3-frontend`, HEAD `25fd27d` (tasks 1-7 landed at
`56a70f7`; a task-7 review fix — `25fd27d`, removing the word "reviewer" from
`AlertPanel.vue`'s open-alert copy and widening `ClaimDetailView.vue`'s error guard so a
failed poll doesn't blank an already-loaded claim — committed itself to the branch while
this task's stack was up, landed by the reviewer working task 7's diff concurrently).
Compose project `stage-3-frontend`. Compose commands ran from the repository root; the one
curl session (logged in as `rob`, forcing the conflict in screenshot 7) ran from `/tmp`
with cookie jar `rob.jar`, the same pattern stage 2's receipts used.

## Clean build

```
$ docker compose -p stage-3-frontend down -v
$ docker compose -p stage-3-frontend up --build -d
$ docker compose -p stage-3-frontend ps
NAME                          IMAGE                     SERVICE    STATUS
stage-3-frontend-api-1        stage-3-frontend-api      api        Up (healthy)
stage-3-frontend-frontend-1   node:22-alpine            frontend   Up
stage-3-frontend-postgres-1   postgres:17-alpine        postgres   Up (healthy)
stage-3-frontend-worker-1     stage-3-frontend-worker   worker     Up
```

Migrate + seed ran automatically on API boot (`docker compose logs api`): `users: sam,
rita, rob` / `claims: 10 created`. The frontend container ran `npm install && npm run dev`
and served Vite on `http://localhost:5173/`.

## Screenshots

All captured with the browser tools (`agent_browser_open`/`snapshot`/`eval`/`screenshot`)
against `http://localhost:5173`, logging in as the seeded users. Several buttons needed an
`agent_browser_eval` DOM `.click()` fallback after a re-render (`@ref` clicks went stale,
as flagged in the task brief); form fields were filled the same way, setting the native
input value and dispatching an `input` event before submit.

1. **`01-login.png`** — the sign-in page at `/login`, unauthenticated.
2. **`02-list-sam.png`** — signed in as `sam`; the claims list with the seed's ten claims,
   the "New draft" button, and the state/open-alerts filters.
3. **`03-blocked-submit.png`** — clicked "New draft", filled only the billed amount
   (`199.00`, payer and service date left blank), clicked "Create draft". On the new
   draft's detail page, **Submit** renders disabled with the hint "Payer is required.;
   Service date is required." — the rule lives on the server; the button just renders the
   reason it sent back.
4. **`04-pending-badge.png`** — `docker compose -p stage-3-frontend stop worker` first, so
   the registration cannot race the screenshot. Created a second draft (payer "Blue Ridge
   Mutual", service date `2026-09-05`, billed `325.00`), clicked Submit. With the worker
   down the claim reaches `SUBMITTED` and the registration badge reads **Pending**,
   verifiably (nothing could have raced it to Done).
5. **`05-done-badge.png`** — `docker compose -p stage-3-frontend start worker`; the worker
   log shows `claim=CLM-6BBB87A2D1DD87B5 status=DONE attempt=1
   event=registration_succeeded`. No manual reload: the detail view's own 3-second poll
   (active because `registration.status` was `pending`) picked up the change and the badge
   now reads **Done** with the clearinghouse submission ID.
6. **`06-rule-error.png`** — signed out `sam`, signed in as `rita`. Opened
   `CLM-A463DF976284860F` (claim 4, Submitted, billed `$450.00`, already registered from
   the seed), clicked "Start review", clicked "Approve", entered `999.00` (above the
   billed amount), clicked the form's Approve button. The panel shows "Approved amount
   cannot exceed the billed amount." both above the actions and under the field; the form
   stays open with `999.00` still in the input.
7. **`07-conflict.png`** — with rita's Approve form still open on claim 4 at the version
   she loaded it at (`2`), a second session (`curl`, cookie jar `/tmp/rob.jar`, logged in
   as `rob`, `X-CSRFToken` read from the jar) posted `{"action": "approve", "version": 2,
   "data": {"approved_amount": "450.00"}}` to `/api/claims/4/transition/` and it landed —
   claim 4 is now `APPROVED` at version 3. Back in rita's stale browser tab, changed the
   open form's amount to `100.00` and clicked Approve again: the transition 409s and the
   `ConflictBanner` reads "This claim changed while you were looking at it. rob approve 8
   seconds ago. It is now Approved." — built from the 409 body's `last_event` and
   `current_state`, nothing hardcoded. The whole actions panel, including the still-open
   Approve form, renders disabled until Reload.
8. **`08-retry-and-alert.png`** — navigated to the seed's failed claim (claim 10,
   `CLM-51FA267932EDA578`, `registration: Failed`, 5 attempts, open alert card visible),
   clicked "Retry registration". The alert card stays on the page through the retry (an
   alert is answered, never cleared — stage 2's decision, unchanged here); by the time the
   screenshot was saved the retry had already reached `registration: Done` and "Start
   review" had unblocked, which is itself evidence the retry worked.
9. **`09-acknowledged.png`** — filled the alert's Note field ("Confirmed at the
   clearinghouse: retried and now registered. No duplicate billing.") and clicked
   "Acknowledge". The alert card now reads "Acknowledged by rita … ” — the failure event
   itself is still shown (history is append-only; acknowledging answers it, it doesn't
   erase it) — and the list's `alert` badge for this claim is gone.
10. **`10-empty.png`** — set the State filter to "Withdrawn" and checked "open alerts
    only" (no withdrawn claim has an open alert). The list renders "No claims match."

## The grep from the spec's done criteria

As written:

```
$ grep -rnE "DRAFT|SUBMITTED|UNDER_REVIEW|INFO_REQUESTED|APPROVED|DENIED|WITHDRAWN|submitter|reviewer" frontend/src
frontend/src/components/ConflictBanner.test.ts:11:          current_state: "UNDER_REVIEW",
frontend/src/api/client.test.ts:21:    const body = { detail: "changed", current_state: "APPROVED", current_version: 3, last_event: null };
```

Both hits are literal values inside Vitest fixtures (`ConflictBanner.test.ts` builds a
sample 409 body to test the banner's rendering; `client.test.ts` builds a sample 409 body
to test `ConflictError` parsing) — test data standing in for what the API would actually
send, not a rule or a state name baked into application source.

With test files excluded, as the task instructed:

```
$ grep -rnE "DRAFT|SUBMITTED|UNDER_REVIEW|INFO_REQUESTED|APPROVED|DENIED|WITHDRAWN|submitter|reviewer" frontend/src --exclude='*.test.ts'
(no output)
```

Empty. `App.vue` renders the signed-in user's role with `{{ session.user.value.role }}` —
it displays whatever string the API's `/api/me/` sends, but the source itself never
spells out "submitter" or "reviewer", so it does not match this pattern; the brief
anticipated this line might or might not show up here, and here it does not.

## Tests

```
$ cd frontend && npm run typecheck
> claims-frontend@0.1.0 typecheck
> vue-tsc --noEmit -p tsconfig.app.json
(no errors)

$ cd frontend && npm test
 RUN  v3.2.7
 ✓ src/api/client.test.ts (6 tests) 10ms
 ✓ src/components/ConflictBanner.test.ts (1 test) 7ms
 ✓ src/components/ActionPanel.test.ts (2 tests) 15ms
 ✓ src/components/ActionForm.test.ts (3 tests) 20ms
 Test Files  4 passed (4)
      Tests  12 passed (12)
```

```
$ cd backend && uv run pytest -q
........................................................................ [ 36%]
........................................................................ [ 73%]
....................................................                     [100%]
196 passed in 38.56s
```

(Postgres reachable on host port 5433 per `backend/.env.example`, up via `docker compose
-p stage-3-frontend up -d postgres`.)

## Teardown

```
$ docker compose -p stage-3-frontend down
$ docker compose -p stage-3-frontend up -d postgres
```
