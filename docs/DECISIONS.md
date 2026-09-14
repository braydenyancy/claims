# Decisions

One line each: what, then why over the rejected alternative.

1. **Vendor module behind a gateway, not a container.** The brief says use the client as-is; one class imports it and names three outcomes. Rejected: wrapping it in an HTTP service.
2. **Registration is a Postgres outbox drained by a worker.** Crash-safe and testable with no broker. Rejected: Celery and Redis for one job; calling the vendor inside the request.
3. **Session login with a CSRF header.** Permissions and the audit trail need an identity. Rejected: tokens in the browser; a trusted header.
4. **One declarative transition table.** Enforcement and the available-actions list read the same rows, so they cannot drift. Rejected: a state-machine dependency.
5. **Row lock plus version check; conflict is 409.** The lock serializes the write, the version catches the stale screen, the body says who changed what. Rejected: either alone.
6. **One event table, same transaction, immutable in the database.** A trigger rejects UPDATE and DELETE. Rejected: separate audit and log tables; application-only immutability.
7. **Claim reference is server-generated, 64 random bits.** It is the clearinghouse lookup key, so it is never reused or chosen by a user.
8. **Submitters act only on their own claims.** The brief is silent; enforced in the queryset, not just the transition.
9. **Money is Decimal, two places, sent as a string.** Never float.
10. **Monorepo, one Django app, worker shares the API image.** Boundaries are modules: the transition table has no Django imports; the gateway is the only vendor importer.
11. **Alerts are a severity on events.** Acknowledging is itself an event and needs a note. Nothing is ever cleared.
12. **Tests are table-driven and few.** One file per requirement proved; the reviewer race runs against real Postgres.
13. **An Unknown outcome becomes UNCERTAIN and is never resubmitted.** The vendor bills every call and has no idempotency, so a reviewer runs a lookup-only reconcile instead. Rejected: automatic retry, which cannot promise at-most-once billing.
14. **Colour and counts come from the API.** Meta carries a tone per state; a summary endpoint carries counts. Rejected: mapping state names to colours in the frontend.
15. **The frontend decides nothing.** Every button, block, and permission is a server flag. Rejected: any client-side rule, even a duplicate one.
