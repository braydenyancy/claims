# Architecture

Four containers and one vendor module. Numbered decisions are in [DECISIONS.md](DECISIONS.md).

```
browser ──/api (same-origin proxy)──▶ frontend (Vite) ──▶ api (Django + DRF) ──▶ postgres
                                                          worker (same image) ──▶ postgres
                                                          worker ──gateway──▶ vendor/clearinghouse.py
```

- **api** enforces every rule. Session cookie auth, CSRF header, JSON only. Submitters see their own claims; reviewers see all.
- **worker** drains the registration outbox. It is the only process that calls the vendor, and it never does so inside a database transaction.
- **frontend** renders what the API says: available actions, blocked reasons, badge tones, dashboard counts. It contains no state or role names.
- **vendor/clearinghouse.py** is the supplied client, unmodified. `clearinghouse/gateway.py` is its only importer and turns its exceptions into `Registered | Rejected | Unknown`.

## Backend modules

| Module | Owns |
|---|---|
| `claims/transitions.py` | The lifecycle table: action, from-states, to-state, role, fields, rule. No Django imports. |
| `claims/services.py` | Every write: create/edit draft, transition, retry, reconcile, acknowledge. Views never touch models directly. |
| `claims/clearinghouse/` | Gateway and worker. |
| `claims/api/` | Serializers, views, the 401/403 split, meta and summary endpoints. |
| `claims/models.py` | `Claim` (state, version, `has_open_alert`), append-only `ClaimEvent`, `Registration` outbox row. |

## A transition, in order

```
request → logged in? (401) → in my scope? (404) → SELECT … FOR UPDATE → owner? (404)
  → version matches? (409 {current_state, current_version, last_event})
  → role allowed? (403) → from-state allowed? (400) → rule passes? (400 {errors})
  → write state, version+1, event, side effects → commit → 200 {claim}
```

Every write shares one transaction. A losing concurrent reviewer waits on the lock, re-reads, fails the version check, and gets the 409 with who changed what. The event table refuses UPDATE and DELETE with a Postgres trigger.

## Registration outbox

```
submit commits [SUBMITTED, event, registration PENDING]
worker: claim_next (SKIP LOCKED, IN_FLIGHT, lease token, attempts+1)
      → lookup(reference): 1 id → adopt, DONE · >1 → HALTED + alert · 0 → register
      → Registered → DONE + info event
      → Rejected   → PENDING with backoff, or FAILED + alert when the budget is spent
      → Unknown    → UNCERTAIN + warning event; never submitted again
reap:   IN_FLIGHT past its lease → UNCERTAIN (a result arriving late is discarded, warning event)
```

Reviewer controls: `retry` re-queues a FAILED row; `reconcile` runs lookup only on an UNCERTAIN row and adopts one id, halts on several, or leaves it uncertain. HALTED has no API route; a person resolves the duplicate at the clearinghouse first. The vendor bills every call and offers no idempotency, so at-most-once billing wins over eventual registration.

## Frontend contract

- `GET /api/meta/` gives labels and a tone (`neutral | info | success | warning | danger`) per state and registration status.
- `GET /api/claims/summary/` gives counts per state over the caller's scope; the list view's chip strip is built from it.
- A claim's `available_actions[]` carries `fields` and `blocked_reason`; blocked actions render disabled, never hidden.
- `can_edit`, `can_retry`, `can_reconcile`, `can_acknowledge`, and `can_create_claims` are the only permission signals the UI reads.
- The detail view polls every 3 s while a registration is pending or in flight.

## Workflows

```
W1 lifecycle   DRAFT ─submit(S)→ SUBMITTED ─start_review(R)→ UNDER_REVIEW ─approve(R)→ APPROVED
                                                            ├─deny(R)→ DENIED
                                                            └─request_info(R)→ INFO_REQUESTED ─provide_info(S)→ UNDER_REVIEW
               DRAFT | INFO_REQUESTED ─withdraw(S)→ WITHDRAWN            (S submitter, R reviewer; last three are final)
W2 transition  request → 401 → 404 → lock → 409 → 403 → 400 → write claim + event → commit
W3 race        A locks, writes, commits → 200 · B waits, re-reads, version differs → 409 {current_state, last_event}
W4 register    submit → PENDING → worker lookup → register → DONE → start_review unblocked
W5 trouble     Rejected → backoff → FAILED (alert) ─retry(R)→ PENDING · Unknown | expired lease → UNCERTAIN ─reconcile(R)→ DONE | HALTED | UNCERTAIN
W6 alert       alert event → has_open_alert → reviewer acknowledges with note → alert_acknowledged event (nothing is cleared)
W7 startup     compose up → postgres healthy → migrate → seed → api healthy → worker polls → frontend serves
```
