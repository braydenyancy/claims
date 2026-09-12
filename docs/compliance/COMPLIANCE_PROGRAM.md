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
- **Out of scope:** Anti-Kickback Statute and Stark Law. Both govern
  referral and physician financial relationships, which a claim review
  workflow does not touch.

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

Placeholder. The audit log, access controls, and monitoring we build
will be documented in `docs/security/` and referenced here.

## 7. Responding to detected offenses and corrective action

Placeholder. Incident response and corrective action procedure to be
written in `docs/procedures/`.
