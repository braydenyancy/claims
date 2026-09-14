# Notes

## Assumptions

Submitters see only their claims; reviewers see all. Drafts may omit payer or service date and may have a zero amount; submission checks all three. Service dates are calendar dates with no time zone. Denial reasons are a fixed demo list. The vendor bills duplicate submissions and does not enforce idempotency: claim reference is a unique lookup key, not a retry token.

## Design

One transition table defines legal states, roles, inputs, and rules. The API uses it to enforce changes and describe available actions; Vue renders those actions without copying the rules; badge colours and the dashboard counts come from the API too, so the frontend contains no state or role names. I chose this small explicit table over a state-machine dependency.

A transition locks the claim row, compares the client's version, then writes the claim and audit event in one transaction. The loser of a reviewer race gets HTTP 409 and the current state. The event table also has an update/delete trigger. A lock alone would serialize writes but give poor stale-screen feedback; versioning alone would not serialize the check and write.

Submission creates a registration outbox row in that same transaction. A worker calls the supplied client outside it, first looking up the reference to adopt an existing ID or detect duplicates. Definite rejections can retry. A timeout with no visible ID, or an expired worker lease, becomes **UNCERTAIN** and cannot submit again. A reviewer can run a lookup-only check: one ID is adopted, multiple IDs halt, and zero IDs remain uncertain for investigation. This protects against a second billed call but may leave a claim unregistered. Without vendor-enforced idempotency, automatic retry cannot guarantee both eventual registration and at-most-once billing. A synchronous request would hold the user waiting and make crash recovery harder; a broker seemed excessive for one job.

The demo sends only reference and amount to the clearinghouse. Session cookies and a same-origin development proxy keep authentication simple; server-side permissions remain authoritative.

## Unfinished and production changes

The UI uses Vite's development server and polls registration status. Before production: serve a built frontend over HTTPS; use a deployment secret, restricted hosts, secure cookies, login throttling and CSRF protection on login; give the audit table a restricted database role; add monitoring, an accessibility pass, and pagination for long histories. Uncertain registrations need an operational resolution procedure. Vendor idempotency or an equivalent acknowledgement protocol would permit safe automated retries; a broker and jittered backoff would help if job volume grows.

Tests target the transition matrix, permissions, a real PostgreSQL reviewer race, audit immutability, and vendor success, rejection, timeout, and recovery.

## AI use

I used AI tools to discuss the design, help implement and review code, and draft tests and documentation. I verified the behavior and can explain the tradeoffs.
