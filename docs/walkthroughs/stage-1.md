# Stage 1 walkthrough: backend core

Four files carry the design. Read them in this order.

## 1. The table: `backend/claims/transitions.py`

The whole lifecycle is the `TRANSITIONS` dictionary near the bottom.
Seven entries, each saying from-states, target, role, input fields,
what gets written onto the claim, and a rule function. There is no
other place a rule lives. The module has no Django import, which is
why states and roles are plain strings at the top; a test pins them to
the Django enums so they cannot drift.

Two things to point at. `available_actions` pre-evaluates the rule for
transitions that need no input, so the UI can show a disabled button
with the reason; that is how "start review" reads "no submission ID
yet". And `_approve_rules` checks type, scale, sign, then ceiling, in
that order, after review found that `0.001` would 500 and `50.005`
would put a different number in the audit log than on the claim.

## 2. The service: `backend/claims/services.py`

Every write goes through `transition()`. The order of checks is the
sentence to say cold: lock the row, check ownership, check version,
check role, check state, filter the input to declared fields, run the
rule. Nothing is written until all of that passes. Then state, version,
and the event commit together or not at all.

Ownership before version: a conflict response carries the claim, and a
caller who is not allowed to see it must never get that far. The
comment above `select_for_update` records that the 409 depends on READ
COMMITTED: the loser blocks on the lock, then re-reads the committed
row and sees the incremented version. Under REPEATABLE READ it would
get a serialization error instead.

## 3. The endpoint: `ClaimViewSet.transition` in `backend/claims/api/views.py`

The view does three things and nothing else: scope the claim so foreign
ones are 404, validate the envelope, and map service exceptions to
status codes. Rule failures are 400 with field errors, wrong role 403,
stale version 409. The 409 body carries the current state and the most
recent event, which is what lets the UI say "Rita approved this at
10:42" rather than "conflict". The explicit `order_by` in `_conflict`
matters: the model's default ordering is ascending, so `first()`
without it would return the create event.

## 4. The race: `backend/claims/tests/test_concurrency.py`

Two real threads, two real connections, a barrier so they arrive
together, both believing the version is 0. Exactly one gets "ok", one
gets "conflict", the version is 1, and there is exactly one decision
event. Remove the row lock and both would pass the version check and
both would write. The second test is the far more common real case: a
reviewer whose tab is a minute stale.

## 5. The trigger: `backend/claims/migrations/0003_claimevent_immutable.py`

UPDATE and DELETE on the event table raise at the database, so a shell
or a bulk ORM call fails the same way the model does. TRUNCATE is not
covered, deliberately: a trigger there breaks the test runner's own
teardown, and the production answer is a database role that lacks the
privilege.

## What review caught before the interview would have

- A reviewer could edit any submitter's draft through PATCH; the owner
  check only guarded submitters. Fixed with a strict creator check.
- An approved amount of `0.001` returned a 500 and `50.005` stored
  `50.01` while recording `50.005` in the audit event. Fixed by
  validating decimal scale where type was already validated.

## Likely live-session extensions

- **Add a `reopen` transition from DENIED.** One tuple in `TRANSITIONS`,
  one row in the literal expected-table test. Gap to name first: the
  table has `writes` but no `clears`, so a reopened claim would keep its
  stale denial reason.
- **Add a third role.** Mostly mechanical, except the list scoping only
  special-cases submitters, so a new role would see everything by
  default. An explicit per-role scope map is the honest fix.
