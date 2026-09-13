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
during the idle sleep is only noticed once it ends; fine at the 1 second
default. An alert is answered, never cleared: acknowledging one requires
a note, is itself an event, and `has_open_alert` drops only once every
alert has a matching acknowledgement. HALTED means the clearinghouse
holds more than one submission for a reference; a human resolves which
is real there, so the API refuses to retry it — only FAILED is
retryable. `test_clearinghouse.py` proves all four outcomes against
`FakeGateway`: rejected, unknown-and-recorded, unknown-and-lost, and
duplicate.

**Deferred.** Celery replacing the poll loop in production; jittered
backoff instead of `2 ** attempts`; a per-claim idempotency key at the
vendor if it ever offers one; a TRUNCATE guard enforced by database role
rather than convention; pagination on `/history/`.

**AI use.** Same as stage 1: design was discussed with an AI assistant
and recorded in `docs/`; implementation followed a written plan with a
subagent per task and a review after each. Every line was read and is
defended by the author.
