# Notes

One command: `docker compose up`. API on 8000, UI on 5173, seeded logins
in the README. Receipts for every stage are under `docs/receipts/`, and
`docs/walkthroughs/` gives the reading order for each stage.

## Assumptions

- Submitters see and act on their own claims only; reviewers see all.
- A draft may be created incomplete and edited until submitted; the submit
  rules are checked at submit, not at creation.
- Denial reasons are a five-value fixed list standing in for standard
  adjustment reason codes.
- Service dates are compared against today in UTC.
- The vendor's `ClearinghouseTimeout` may or may not have recorded a
  submission; the design treats it as "unknown" and looks up before it
  ever retries.
- Only FAILED registrations are retryable; HALTED (more than one
  submission at the clearinghouse) needs a human at the clearinghouse
  first.

## Main decisions, and what was rejected

- **One declarative transition table** (`transitions.py`, no Django
  imports) drives both enforcement and the available-actions list, so
  they cannot drift. Rejected: `django-fsm` and relatives, a dependency to
  defend line by line with a messy maintenance history.
- **Row lock plus version check**, conflict is 409 with the current state
  and last event. Rejected: lock only (a stale screen gets an unhelpful
  "invalid transition"); version only (does not serialize the write).
- **Audit events in the same transaction, immutable at the database** by
  trigger. Rejected: separate audit and system-log tables; application-only
  immutability, which a shell bypasses.
- **Transactional outbox and a worker process** that always looks up
  before it submits. Rejected: Celery and Redis (a broker for one job;
  named below as the production swap); calling the vendor inside the
  request (a lock held across network I/O, and the ID lost on a crash).
- **Session cookies behind a Vite proxy**, so the SPA and API share an
  origin. Rejected: tokens in the browser (XSS-exposed); CORS (never
  needed once the origin is shared).
- **The UI decides nothing.** State labels, capabilities (`can_edit`,
  `can_create_claims`, `can_acknowledge`, `can_retry`) and every action
  come from the API; a grep for state and role names over the frontend
  source returns nothing. Rejected: a client-side copy of any rule.
- **No Pinia, no component library.** One composable holds the session.

Full rationale: `docs/architecture/DECISIONS.md`.

## Unfinished

- Pagination controls beyond a "showing N of M" hint; `/history/` is not
  paginated.
- A production build and static serving of the frontend; the Vite dev
  server behind compose is the deliverable.
- Real-time push; the detail view polls every three seconds while a
  registration is pending.
- An accessibility pass.

## Before running this in production

- Replace the poll loop with Celery or an equivalent, keep the outbox.
- Jittered backoff; a client-side vendor timeout is already in place.
- Separate database roles so the audit table's immutability is enforced by
  privilege (including TRUNCATE) rather than trigger and convention.
- Login throttling and `csrf_protect` on the login route; a secret-key
  guard that refuses the dev default when `DEBUG` is off; `ALLOWED_HOSTS`
  narrowed; HTTPS-only cookies.
- The one window the design cannot close: a vendor call that outlives its
  lease can let a second worker submit again. It needs a vendor-side
  idempotency key, which this vendor does not offer, so the timeout keeps
  every call well inside the lease and the case is caught afterwards as
  `duplicate_submission`.

## How AI tools were used

Design was discussed with an AI assistant and recorded in `docs/`
(decisions, workflows, a spec per stage). Implementation followed a
written plan per stage with an AI subagent per task and an independent
AI review of every diff, whose findings were fixed before the next task.
Every review finding and every ruling on it is in the commit history.
Every line was read and is defended by the author.

---

## Appendix: per-stage detail

### Stage 1: backend core

**Assumptions.** Submitters see and act on their own claims only; reviewers
see all. A draft may be created incomplete and edited (PATCH) until
submitted; the submit rules are checked at submit. Denial reasons are a
five-value fixed list standing in for standard adjustment reason codes.
Service dates are compared against today in UTC.

**Decisions.** The lifecycle is one declarative table (`transitions.py`, no
Django imports) read by both enforcement and the available-actions list,
so they cannot drift. Every state change runs in `services.transition`
under `select_for_update` plus a version check, and writes its audit
event in the same transaction; a stale client gets 409 with the current
state and the last event. Ownership is checked before the version so that
response never describes a claim the caller cannot see. Draft edits
require being the creator, regardless of role; the available-actions list
is a UI convenience, not the authorization boundary. History is
append-only at the model and by a Postgres trigger. Session auth, Django
defaults only. Full rationale and rejected alternatives:
`docs/architecture/DECISIONS.md`.

**Tests.** Table-driven, one file per requirement proved: the transition
matrix (every action × state × role), rule cases, a two-thread race
against real Postgres, trigger immutability, and a handful of HTTP paths.
Two guard tests pin the rule module's state, role and denial lists to the
Django model's, and one spells out all seven transitions as literals so
the table itself is proved, not only the service's obedience to it.

### Stage 2: clearinghouse registration

**Decisions.** The worker never calls `register` without calling
`lookup` first: zero IDs, submit; one ID, adopt it; more than one, stop
and raise `duplicate_submission`. One rule covers a timeout, a crashed
worker, and a double run at once, since all three just leave a different
count of submissions at the clearinghouse and the lookup reacts the same
way regardless of cause. Three short transactions — `claim_next` (mark
IN_FLIGHT), `record` (write the outcome), `reap` (reclaim an expired
lease) — bound the writes; `process` calls the vendor with none of them
open. Each claim gets a fresh `lease_token` on IN_FLIGHT; `record`
applies an outcome only if the token still matches, so a worker outlived
by its lease can't overwrite a newer attempt's result — its late write
becomes a `registration_stale_result` warning event instead. Worker
shutdown on SIGTERM/SIGINT is bounded by `POLL_SECONDS`, since a signal
during the idle sleep is only noticed once it ends, and, after a
timed-out vendor call, by however long that abandoned call takes to
return, since the interpreter joins its thread at exit; Docker's stop
grace period covers the realistic case. An alert is answered, never
cleared: acknowledging one requires
a note, is itself an event, and `has_open_alert` drops only once every
alert has a matching acknowledgement. HALTED means the clearinghouse
holds more than one submission for a reference; a human resolves which
is real there, so the API refuses to retry it — only FAILED is
retryable. `test_clearinghouse.py` proves all four outcomes against
`FakeGateway`: rejected, unknown-and-recorded, unknown-and-lost, and
duplicate. Acknowledging an alert does not bump the claim's `version`: it
is an event about the record, not a lifecycle transition, so it cannot
make another reviewer's open form stale. A successful retry leaves the
alert open on purpose — the registration succeeding is not an answer to
"why did this fail five times", and only a reviewer's note closes it.

**The window this design cannot close.** The lease token protects the
write, not the call. If a vendor call outlives its lease, the reaper
returns the row to PENDING while the first worker is still talking to the
clearinghouse; a second worker then looks up before the first one's
submission lands, sees nothing, and submits again — two billed
submissions, caught afterwards as `duplicate_submission` but not
prevented. `CALL_TIMEOUT_SECONDS` (20s) keeps every call far inside
`LEASE_SECONDS` (60s), so opening the window needs a vendor outage longer
than the lease. Closing it outright needs an idempotency key the vendor
does not offer.

**Deferred.** Celery replacing the poll loop in production; jittered
backoff instead of `2 ** attempts`; a per-claim idempotency key at the
vendor if it ever offers one; a TRUNCATE guard enforced by database role
rather than convention; pagination on `/history/`.

### Stage 3: frontend

**Decisions.** The dev server proxies `/api` to the API container, so
the browser and API share an origin: the session cookie is first-party,
CSRF is one header read from the cookie, and CORS never came up.
`client.ts` maps every response into one of three typed errors —
`ConflictError` (409), `ValidationError` (400, flattened to `{field:
message}`), and the base `ApiError` — so callers catch by class, not by
message-sniffing. Every action button and its form come straight from
`available_actions` and its field schema; a blocked action renders
disabled with `blocked_reason` as its hint, never hidden. `meta`,
`can_edit`, `can_create_claims`, each alert's `can_acknowledge`, and
`registration.can_retry` carry every state, denial reason, and role
decision the UI needs: the alert cards and the retry button read the
detail payload instead of re-deriving an acknowledgement from history or
a capability from a status. So no state or role name lives in the
frontend source — `grep -rnE
"DRAFT|SUBMITTED|UNDER_REVIEW|INFO_REQUESTED|APPROVED|DENIED|WITHDRAWN|submitter|reviewer"
frontend/src` returns nothing. The conflict banner is built from the 409
body; the detail view polls every 3 seconds while registration is
pending or in flight. Every write to the claim goes through the same
sequence in `useAsync` that the reads use, so a slow poll cannot
overwrite a fresh action, and rapid filter changes never flash an old
result. An unauthenticated request answers 401 rather than 403, so a
write whose session has expired redirects to sign-in exactly as a read
does, while a 403 stays an inline "not allowed" message. The router
guard treats a failed session check as signed out rather than blanking
the page. Every action failure surfaces visibly — inline field errors
when a form is open, a panel-level message for fieldless actions like
Submit — and a conflict freezes the whole panel, including an open form,
until reload.

**Deferred.** Production build and static serving; pagination controls
beyond "next page"; real-time push; an accessibility pass; the backend
hygiene list from stages 1 and 2 (Celery, jittered backoff, a vendor
idempotency key, a TRUNCATE guard, `/history/` pagination).
