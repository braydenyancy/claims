# Notes

## Stage 1: backend core

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

**Unfinished after stage 1.** Clearinghouse registration (stage 2) and
the frontend (stage 3). `start_review` is blocked until stage 2 stamps
a submission ID; the seed stamps one directly where a sample needs it.

**AI use.** Design was discussed with an AI assistant and recorded in
`docs/`; implementation followed a written plan with a subagent per task
and a review after each. Every line was read and is defended by the
author.

## Stage 2: clearinghouse registration

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

**AI use.** Same as stage 1: design was discussed with an AI assistant
and recorded in `docs/`; implementation followed a written plan with a
subagent per task and a review after each. Every line was read and is
defended by the author.

## Stage 3: frontend

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

**AI use.** Same as stages 1 and 2: design was discussed with an AI
assistant and recorded in `docs/`; implementation followed a written plan
with a subagent per task and a review after each. Every line was read
and is defended by the author.
