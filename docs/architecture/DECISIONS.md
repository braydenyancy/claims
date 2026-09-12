# Decisions

Numbered so workflows can cite them. Each entry: what, why, rejected.

**D1. Vendor module is imported behind a gateway, not containerized.**
The brief says use the client as-is. A gateway class is the only code
that imports it and converts its two exceptions into an explicit
outcome: registered, rejected, or unknown. Rejected: wrapping it in an
HTTP service (code the brief did not ask for; no longer "the provided
client").

**D2. Registration runs in a separate worker over a Postgres outbox.**
`submit` commits the state change and a pending registration row in
one transaction. A worker process drains the outbox. Crash-safe,
testable, no broker. Rejected: Celery + Redis (extra infrastructure
for one job; named in NOTES as the production swap); synchronous in
the request (holds a lock during network I/O, loses the ID on crash).

**D3. Django session login, default only.** Seeded users, one login
endpoint, DRF session authentication, CSRF header from the frontend.
Identity is required because permissions are server-enforced and the
audit log records the actor. Rejected: tokens in the browser
(XSS-exposed); a trusted header (not enforcement).

**D4. One declarative transition table is the single source of rules.**
Action to from-states, to-state, role, validator. Drives both
enforcement and the available-actions response, so they cannot drift.
Rejected: `django-fsm` family (dependency with a messy maintenance
history, harder to defend line by line).

**D5. Concurrency is a row lock plus a version check; conflict is 409.**
`select_for_update` makes check-and-write atomic. A `version` field the
client echoes back catches the stale screen. The 409 body carries the
current state and the last event so the UI can say who did what.
Rejected: lock only (stale client gets an unhelpful "invalid
transition"); version only (does not serialize the write).

**D6. One event table, written in the same transaction, immutable at
the database.** User transitions and worker outcomes share a shape.
A Postgres trigger rejects UPDATE and DELETE. Rejected: separate audit
and system-log tables (two histories to reconcile); application-only
immutability (does not stop a shell).

**D7. Claim reference is server-generated and unique.** It is the
idempotency key the clearinghouse recognises, so it must never be
reused or user-chosen.

**D8. Submitters act only on their own claims. Assumption.** The brief
is silent. Enforced in the queryset, not only in the transition.

**D9. Money is Decimal.** Never float. Passed to the clearinghouse as
a string, as its signature asks.

**D10. Monorepo, one Django app, worker shares the API image.** The
domain is one aggregate. Boundaries live in modules: the transition
table has no Django imports; the gateway is the only vendor importer.

**D11. Alerts are a severity on events.** `info`, `warning`, `alert`.
Alerts: retry budget exhausted, more than one submission ID found.
Acknowledging an alert is an event and requires a note. System events
are visible to submitters and reviewers alike.

**D12. Tests are table-driven and few.** `pytest` + `pytest-django`.
Five files, one per requirement proved: transitions (parameterized
over every action, state, role), concurrency (two threads, real
Postgres), clearinghouse (fake gateway, every outcome, double run),
audit (immutability), API (a handful of end-to-end paths).
