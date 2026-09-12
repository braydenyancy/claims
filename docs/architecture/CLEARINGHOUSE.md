# Clearinghouse boundary

## What they hand us

A Python module, `clearinghouse.py`, to be used as-is. Two functions:

- `submit(claim_reference, amount) -> submission_id`. Slow (0.2 to 2s).
  Every successful call creates a new billed submission, even for a
  reference already submitted.
- `lookup(claim_reference) -> [submission_id, ...]`. Every submission
  recorded for a reference, oldest first.

Two failure modes, and they are not symmetric:

| outcome | recorded at clearinghouse? | safe to retry? |
|---|---|---|
| `ClearinghouseError` | no | yes |
| `ClearinghouseTimeout` | maybe | **no** |

## Where we sit

We are the system of record for the claim lifecycle. The clearinghouse
is the system of record for registration. Submitters create claims in
our system; we register them with the clearinghouse; our reviewers act
on them. Only registration crosses the boundary, and only two fields
cross it: the reference and the amount. No PHI leaves.

## Goal

When a claim is submitted, register it with the clearinghouse exactly
once and store the submission ID on the claim.

Exactly once is the whole problem. It decomposes into three rules:

1. The claim reference is unique and server-generated. It is the
   idempotency key the clearinghouse recognises.
2. Never retry a timeout blind. Call `lookup` first; adopt the ID if
   one exists, retry only if none does, halt for a human if several.
3. Never call `submit` inside a database transaction or while holding
   a lock on the claim.

Everything else about registration (when it runs, what the user sees,
how failures surface) is our design choice and is documented as we
make it.
