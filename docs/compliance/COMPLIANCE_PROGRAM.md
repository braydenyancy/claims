# HIPAA Compliance Program

Rules for building this demo. Short on purpose; each section points to
where the detail will live. Structure follows the seven elements of an
effective compliance program (HHS OIG Compliance Program Guidance).

## Scope

- **HIPAA**, including **HITECH**, which supplies the breach
  notification rule and the civil penalty tiers referenced below.
- **False Claims Act.** As an RCM operation, every claim we help
  submit is a representation to a payer. Controls in this repository
  (approved amount never exceeds billed, denial reasons from a fixed
  list, no duplicate registration, every decision attributed) exist to
  keep that representation accurate.
- **Out of scope for this demo:** Anti-Kickback Statute and Stark Law.
  Both govern referral and physician financial relationships, which
  are outside what this claim review workflow models.

## 1. Compliance officer and committee

Brayden Yancy is the designated Compliance Officer and leads the
compliance committee. The committee is Brayden and the AI assistant
working in this repository. The officer decides; the assistant
proposes, documents, and flags.

## 2. Written policies, procedures, and standards

Compliance is not a feeling. It is written policies (what we require),
procedures (how we do it), and standards (what "done" looks like),
kept in this repository and referenced by the rest of this document.

- Policies: `docs/policies/`
- Procedures: `docs/procedures/`
- Security controls: `docs/security/`

A rule that is not written down here does not exist.

## 3. Training

Every contributor, human or agent, reads this document and the
policies it links before touching code that handles claim data.
Training means understanding why a policy exists, not just that it
does.

## 4. Communication

Internal employees and internal services communicate through defined,
documented channels. Ambiguity in a rule is raised to the Compliance
Officer, not resolved silently.

## 5. Disciplinary guidelines

Placeholder. Reference to be added: public disciplinary standards
for HIPAA violations (HHS OCR civil penalty tiers, 45 CFR 160.404).

## 6. Internal monitoring and auditing

Every claim state change and every clearinghouse registration outcome
writes an append-only `ClaimEvent` tagged `info`, `warning`, or `alert`;
the event table in `docs/specs/2026-09-12-stage-2-clearinghouse.md` and
workflows W4 and W5 in `docs/architecture/WORKFLOWS.md` name every
action and its severity. The worker's log line for each attempt
(`docker compose logs worker`) is the same audit trail as it happens,
not only after the fact.

## 7. Responding to detected offenses and corrective action

An alert (`registration_failed`, `duplicate_submission`) is answered by
a reviewer through `POST /acknowledge/`, which requires a note and is
itself recorded as an event (W6 in `docs/architecture/WORKFLOWS.md`) —
nothing is ever silently cleared. A HALTED registration additionally
requires a human to resolve the duplicate at the clearinghouse itself
before that acknowledgement, since the API has no route that retries it.
