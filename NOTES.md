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
