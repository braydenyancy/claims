# Stage 1: Backend core

Status: complete. Decisions: D3 to D10, D12. Workflows: W1, W2, W3, W7.

## Goal

The full claim lifecycle works over the API with curl. Rules, roles,
conflicts, and history are enforced and tested. No clearinghouse call
yet; `start_review` stays blocked because no submission ID exists.

## Out of scope

Registration worker (stage 2). Frontend (stage 3). Alerts UI (stage 3).
Pagination beyond DRF defaults.

## Cuts

Each cut is one commit and runnable on its own.

- [x] **1.1 Skeleton.** `compose.yaml` with postgres and api. Django
      project, DRF installed, health endpoint. `docker compose up`
      answers `GET /api/health/`.
- [x] **1.2 Models and migration.** `User.role`, `Claim`, `ClaimEvent`.
      Trigger rejecting UPDATE/DELETE on `ClaimEvent`. Check constraint
      `approved_amount <= billed_amount`.
- [x] **1.3 Transition table and service.** `transitions.py` (no Django
      imports) and `services.transition()`. Parameterized tests over
      every action × state × role. Rule tests per transition.
- [x] **1.4 Seed.** Idempotent `seed` command: one submitter, two
      reviewers, a handful of claims across states. Runs on startup.
- [x] **1.5 Auth and claim API.** Login/logout, `GET /me`. Claim list
      with `?state=`, create draft, detail with `available_actions`,
      history. Submitter scope enforced in the queryset.
- [x] **1.6 Transition endpoint.** `POST /claims/{id}/transition/`
      with `{action, version, data}`. Row lock, version check, 409
      body. Concurrency test with two threads against Postgres.
- [x] **1.7 NOTES.md paragraph** for stage 1 while it is fresh.

## Data model

```
User      role: submitter | reviewer
Claim     reference (unique, server-generated) · payer · service_date
          billed_amount · approved_amount? · denial_reason?
          state · version · submission_id? · created_by · created_at
ClaimEvent claim · actor? · action · from_state · to_state
          data (json) · severity · created_at
```

Denial reasons (fixed list): `not_covered`, `duplicate`,
`insufficient_documentation`, `out_of_network`, `timely_filing`.

## API

```
POST /api/auth/login/            {username, password}
POST /api/auth/logout/
GET  /api/me/
GET  /api/claims/?state=
POST /api/claims/                {payer, service_date, billed_amount}
GET  /api/claims/{id}/           claim + available_actions + registration
PATCH /api/claims/{id}/          {payer?, service_date?, billed_amount?}  drafts only
GET  /api/claims/{id}/history/
POST /api/claims/{id}/transition/ {action, version, data}
```

`available_actions` is a list of `{action, label, fields}` computed
from the transition table for the current user and current state.

409 body: `{detail, current_state, current_version, last_event}`. Malformed requests return 400 with the same {detail, errors} shape as rule failures.

## Done when

- Every row of W1 is exercised by a test and by curl.
- Two concurrent approves yield one 200 and one 409.
- `UPDATE claims_claimevent` fails at the database.
- A submitter cannot read or act on another submitter's claim.
- `docker compose up` on a clean checkout reaches a seeded, working API.

## Tests (D12)

`test_transitions.py`, `test_concurrency.py`, `test_audit.py`,
`test_api.py`. `test_clearinghouse.py` arrives in stage 2.
