# Company context

Ortho Med does Revenue Cycle Management in the No Surprises Act (NSA)
niche: after ordinary claim negotiation fails, the NSA dispute path
begins, and the company runs it like a court case. File, put evidence
on the table, receive a settlement decision. A large share of revenue
sits there. (TDI is assumed to mean the Texas Department of Insurance,
which runs the state-level surprise billing process. Unconfirmed.)

Volume is 150,000 claims a year, heading to 200,000 to 300,000. IT was
stood up a year ago to scale software instead of headcount. Three
towers: Infrastructure, Software Development (the NSA/TDI platform),
and Data (claim status, location, lineage; no data lake yet).
Capability maturity is about 2 of 5, moving toward 3.

## What this means for the demo

- **Audit history is evidence.** In a court-case model the record of
  who did what, when, and with what data is the product, not a log.
  Immutability and atomicity with the state change are non-negotiable.
- **Lineage is a stated gap.** An append-only event stream per claim is
  lineage. Design it so the Data tower could read it directly.
- **Volume is modest for Postgres, real for the clearinghouse.** 300,000
  a year is about 1,200 registrations a working day at up to 2s each.
  The worker needs a concurrency knob, not a queue rewrite.
- **Maturity 2 to 3 means written, repeatable procedure.** Docs-first
  is not overhead here; it is the direction the company said it is
  heading.
