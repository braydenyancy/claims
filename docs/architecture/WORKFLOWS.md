# Workflows

Linear arrow chains. Failure exits branch off the happy path and are
marked with `✗`. Each cites the decisions it depends on.

## W1. Claim lifecycle (D4)

```
DRAFT ─submit(S)→ SUBMITTED ─start_review(R)→ UNDER_REVIEW ─approve(R)→ APPROVED
                                                          ├─deny(R)→ DENIED
                                                          └─request_info(R)→ INFO_REQUESTED
INFO_REQUESTED ─provide_info(S)→ UNDER_REVIEW
DRAFT | INFO_REQUESTED ─withdraw(S)→ WITHDRAWN
```
S = Submitter, R = Reviewer. APPROVED, DENIED, WITHDRAWN are final.

## W2. Transition request (D3, D4, D5, D6, D8)

```
request → session auth → scope check (own claim?) → load claim FOR UPDATE → owner? → version matches?
  → action in table? → from-state allowed? → role allowed? → rule passes?
  → write new state + version+1 → write event → commit → 200 {claim}
```
- ✗ not logged in → 403 (session auth sends no auth challenge)
- ✗ not owner (submitter) → 404
- ✗ version mismatch → 409 {current state, last event}
- ✗ wrong role → 403 · unknown action / wrong from-state → 400
- ✗ rule fails → 400 {field errors}
- ✗ malformed request (bad decimal, negative version) → 400 {detail, errors}

## W3. Concurrent action (D5)

```
A: request ─┐
            ├→ A takes lock → A writes → A commits → 200
B: request ─┘  B waits on lock → B re-reads → version mismatch → 409
```
B's UI shows "A approved this at 10:42. Reload to see the current state."

## W4. Registration, happy path (D1, D2, D6, D7)

```
submit commits [state=SUBMITTED, event, registration=PENDING]
  → worker claims row (SKIP LOCKED, IN_FLIGHT, attempt+1)
  → lookup(reference) (none found)
  → gateway.submit(reference, amount) → REGISTERED(id)
  → store id on claim → registration=DONE → event(info, registration_succeeded)
  → start_review now allowed
```

## W5. Registration, failure and reconcile (D1, D2, D11)

```
every attempt: lookup first → 1 id: adopt · >1: HALTED · 0: register
gateway outcome:
  REJECTED  → attempts < budget? → PENDING with backoff → event(warning)
              ✗ budget spent → FAILED → event(alert, registration_failed)
  UNKNOWN   → lookup(reference)
              → 0 ids → treat as REJECTED (retry is safe)
              → 1 id  → adopt → DONE → event(info, registration_reconciled)
              → >1 id → HALTED → event(alert, duplicate_submission)
stale IN_FLIGHT (older than lease) → reaper → back to PENDING → next attempt runs lookup first
stale lease result → discarded → event(warning, registration_stale_result)
```

## W6. Alert lifecycle (D11)

```
event(alert) written → visible on claim detail and in list filter
  → reviewer acknowledges with note → event(info, alert_acknowledged, {note})
```
Nothing is cleared. The acknowledgement is the answer, on the record.

## W7. Startup

```
docker compose up → postgres ready → migrate → seed (idempotent)
  → api serves → worker polls → frontend serves
```
