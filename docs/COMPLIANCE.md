# Compliance

What this demo does about the rules a claim review system lives under. Structured on the HHS OIG's seven elements, cut to what the code shows.

## Scope

- **HIPAA and HITECH.** Claim data is protected health information. The vendor receives only the claim reference and amount, the minimum necessary for registration.
- **False Claims Act.** Every claim we help submit is a representation to a payer. The controls below keep that representation accurate and attributable.
- **Out of scope.** The Anti-Kickback Statute and Stark Law govern referral and physician financial relationships, which this workflow does not model.

## The seven elements, as built

1. **Compliance officer.** Brayden Yancy is the designated Compliance Officer for this repository and leads its compliance committee.
2. **Written standards.** [ARCHITECTURE.md](ARCHITECTURE.md) and [DECISIONS.md](DECISIONS.md) are the standards; a rule that is not written there does not exist.
3. **Training.** Anyone changing code that handles claim data reads those two documents first.
4. **Communication.** Ambiguity in a rule is raised to the Compliance Officer, never resolved silently.
5. **Enforcement.** Roles are enforced server-side on every write; a submitter cannot see or act on another submitter's claim; an approved amount can never exceed the billed amount, checked in the rule and in a database constraint.
6. **Monitoring and auditing.** Every state change, edit, registration attempt, and acknowledgement is an append-only event with an actor, and the database refuses to update or delete one. The worker's log line per attempt is the same trail as it happens.
7. **Corrective action.** A failed or duplicate registration raises an alert that a reviewer must acknowledge with a note, on the record. An uncertain registration is never resubmitted, so the payer is never billed twice; a reviewer resolves it with a lookup-only check.
