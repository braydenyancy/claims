# Stage 2: Clearinghouse registration

Status: complete. Decisions: D1, D2, D6, D7, D11. Workflows: W4, W5, W6.

## Goal

A submitted claim is registered with the clearinghouse exactly once, its
submission ID lands on the claim, `start_review` unblocks, and every
outcome (success, retry, failure, reconciliation, halt) is visible in
the claim's history and on the API. Nothing calls the vendor module
except one gateway class, and nothing calls it inside a transaction.

## Out of scope

Frontend (stage 3). Real paging for alerts. Multiple worker threads in
one process (concurrency comes from running more worker containers;
`SKIP LOCKED` makes that safe).

## The rule that matters

Never call `submit` without calling `lookup` first. If the clearinghouse
already holds exactly one ID for our reference, adopt it. If it holds
none, submit. If it holds more than one, stop and raise an alert; money
may have been spent twice and a human decides. This one rule covers the
timeout case, the crashed-worker case, and the double-run case at once.

## Data model

```
Registration  claim (one-to-one) · status: PENDING | IN_FLIGHT | DONE | FAILED | HALTED
              attempts · next_attempt_at · in_flight_since · last_error
              created_at · updated_at
Claim         + has_open_alert (bool, set when an alert event is written,
                cleared when acknowledged)
```

Backoff: `2 ** attempts` seconds, budget 5 attempts, lease 60 seconds.
All three are settings, demo-scaled.

## Gateway

`claims/clearinghouse/gateway.py`. One protocol, two implementations.

```
Outcome    = Registered(submission_id) | Rejected(reason) | Unknown(reason)
Gateway    .register(reference, amount: str) -> Outcome
           .lookup(reference) -> list[str]
Vendor     the only importer of vendor/clearinghouse.py; maps
           ClearinghouseError → Rejected, ClearinghouseTimeout → Unknown
Fake       scripted outcomes and an in-memory lookup table, for tests
```

## Worker

`claims/clearinghouse/worker.py`, run by `manage.py run_worker [--once]`.

1. `claim_next()`: one short transaction. `SELECT ... FOR UPDATE SKIP
   LOCKED` on PENDING rows due now → mark IN_FLIGHT, attempts + 1, commit.
2. `process(registration, gateway)`: no transaction open. `lookup`
   first; adopt if one ID; halt if several; otherwise `register`.
3. `record(registration, outcome)`: one transaction. Update the
   registration and claim, write the event, set or clear the alert flag.
4. `reap()`: IN_FLIGHT rows older than the lease go back to PENDING with
   a warning event. Their next attempt does step 2, so the lookup catches
   anything the dead worker actually sent.

| outcome | registration | event | severity |
|---|---|---|---|
| Registered | DONE, ID on claim | registration_succeeded | info |
| adopted from lookup | DONE, ID on claim | registration_reconciled | info |
| Rejected, attempts < budget | PENDING, backoff | registration_retry | warning |
| Rejected, budget spent | FAILED | registration_failed | alert |
| lookup returns > 1 | HALTED | duplicate_submission | alert |
| reaped | PENDING | registration_recovered | warning |

Enqueue: `services.transition` on `submit` creates the PENDING row in
the same transaction as the state change. Rolled back together.

## API

```
GET  /api/claims/{id}/            registration: {status, attempts, last_error,
                                   submission_id, next_attempt_at}
GET  /api/claims/?alert=open      claims with has_open_alert
POST /api/claims/{id}/registration/retry/   reviewer · FAILED → PENDING · event
POST /api/claims/{id}/acknowledge/          reviewer · {event_id, note} · event
                                   alert_acknowledged · clears has_open_alert
```

HALTED is not retryable through the API. A human resolves it at the
clearinghouse and acknowledges the alert with a note saying what was done.

## Cuts

- [x] **2.1 Registration model.** Migration, `has_open_alert`, enqueue on
      submit inside the transaction. Test: submit rolls back the
      registration row with the state change.
- [x] **2.2 Gateway.** Outcome types, `Vendor`, `Fake`. Test the vendor
      mapping by patching the vendor module's `random` and `sleep` at
      test time; the file itself stays untouched.
- [x] **2.3 Worker core.** `claim_next`, `process`, `record`. Tests with
      `Fake`: every row of the table above; lookup-before-submit; the same
      registration processed twice makes one `register` call; two workers
      claim different rows.
- [x] **2.4 Reaper and runtime.** `reap`, `run_worker`, compose `worker`
      service (same image), seed creates real registrations (one left
      PENDING so the worker registers it on boot).
- [x] **2.5 API.** Registration block, retry, acknowledge, alert filter.
- [x] **2.6 Close.** NOTES.md stage 2 paragraph, receipts showing a
      timeout followed by a reconcile in the worker log, spec closure,
      compliance program sections 6 and 7 pointed at the alert lifecycle.

## Done when

- Under compose, a newly submitted claim reaches DONE with an ID without
  human action, and `start_review` is offered.
- After any sequence of worker restarts, `lookup(reference)` returns
  exactly one ID for every DONE claim.
- Killing the worker mid-flight and restarting produces no second
  submission.
- Every registration outcome is an event on the claim's history.
- A FAILED registration shows on the API with a working retry; a HALTED
  one shows an open alert that acknowledgement with a note closes.

## Tests (D12)

`test_clearinghouse.py` for 2.2 to 2.4; additions to `test_api.py` for
2.5; one line in `test_transitions.py` for the enqueue.
