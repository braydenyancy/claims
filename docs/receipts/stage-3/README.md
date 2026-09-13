# Stage 3 receipts

Recorded 2026-09-13 on branch `stage-3-frontend`, HEAD `25fd27d` (tasks 1-7 landed at
`56a70f7`; a task-7 review fix — `25fd27d`, removing the word "reviewer" from
`AlertPanel.vue`'s open-alert copy and widening `ClaimDetailView.vue`'s error guard so a
failed poll doesn't blank an already-loaded claim — committed itself to the branch while
this task's stack was up, landed by the reviewer working task 7's diff concurrently).
Compose project `stage-3-frontend`. Compose commands ran from the repository root; the one
curl session (logged in as `rob`, forcing the conflict in screenshot 7) ran from `/tmp`
with cookie jar `rob.jar`, the same pattern stage 2's receipts used.

**Updated after the final-review fix wave** (backend `93aac6b`, frontend the commit that
carries this file): screenshot 6 retaken, the spec's grep re-run and now empty, and both
suites re-run at their new counts. Everything else below is the original 2026-09-13
record and was not re-captured.

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
6. **`06-rule-error.png`** — **retaken 2026-09-13 after the final-review fixes**, with
   `docker compose up -d api frontend` and the same browser tools. Signed in as `rita`,
   opened `CLM-1B899336F7082414` (claim 5, Under review, billed `$900.00`), clicked
   "Approve", entered `1500.00` (above the billed amount), submitted the form. The rule
   error "Approved amount cannot exceed the billed amount." now appears **once**, under
   the field it belongs to, with the form still open and `1500.00` still in the input —
   the panel-level copy is suppressed while a form is up, so the same sentence is no
   longer printed twice. Counted in the page at capture time:
   `[...document.querySelectorAll(".error, .field-error")].length === 1`.
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

Re-run after the final-review fixes, exactly as the spec writes it:

```
$ grep -rnE "DRAFT|SUBMITTED|UNDER_REVIEW|INFO_REQUESTED|APPROVED|DENIED|WITHDRAWN|submitter|reviewer" frontend/src
(no output)
```

It returned nothing. The two hits it used to have were Vitest fixtures standing in for
what the API would send (`ConflictBanner.test.ts` and `client.test.ts` each built a sample
409 body); both now use the placeholder `STATE_A`, which reads as a state name to the
component under test and to nothing else. `App.vue` renders the signed-in user's role with
`{{ session.user.value.role }}` — it displays whatever string `/api/me/` sends, and the
source itself never spells a role out, so it does not match either.

## Tests

Re-run after the final-review fixes.

```
$ cd frontend && npm run typecheck
> claims-frontend@0.1.0 typecheck
> vue-tsc --noEmit -p tsconfig.app.json
(no errors)

$ cd frontend && npm test
 RUN  v3.2.7
 ✓ src/api/client.test.ts (6 tests) 9ms
 ✓ src/components/ConflictBanner.test.ts (3 tests) 10ms
 ✓ src/composables/useAsync.test.ts (3 tests) 15ms
 ✓ src/components/ActionPanel.test.ts (3 tests) 20ms
 ✓ src/components/ActionForm.test.ts (3 tests) 22ms
 ✓ src/components/AlertPanel.test.ts (2 tests) 29ms
 Test Files  6 passed (6)
      Tests  20 passed (20)
```

```
$ cd backend && uv run pytest -q
........................................................................ [ 36%]
........................................................................ [ 72%]
........................................................                 [100%]
200 passed in 39.20s
```

(Postgres reachable on host port 5433 per `backend/.env.example`, up via `docker compose
up -d postgres`.)

## Teardown

```
$ docker compose -p stage-3-frontend down
$ docker compose -p stage-3-frontend up -d postgres
```

After the screenshot-6 retake, the two services it needed were stopped again and postgres
left up for the test suite:

```
$ docker compose up -d api frontend
$ docker compose stop api frontend
```
