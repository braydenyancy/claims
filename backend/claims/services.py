"""Claim writes and their audit events share a transaction."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from . import transitions
from .clearinghouse.gateway import Gateway
from .models import Claim, ClaimEvent, Registration, RegistrationStatus, Role, Severity, State, User

log = logging.getLogger("claims.services")


class TransitionError(Exception):
    """Base for refused transitions."""


class ConflictError(TransitionError):
    """The claim changed since the caller last saw it."""

    def __init__(self, claim: Claim):
        self.claim = claim
        super().__init__("Claim was modified by someone else.")


class NotAllowed(TransitionError):
    """Wrong role, wrong owner, wrong state, or unknown action."""

    def __init__(self, message: str, status_code: int = 403):
        self.status_code = status_code
        super().__init__(message)


class RuleViolation(TransitionError):
    """The transition's rule did not hold. errors maps field to message."""

    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__("Transition rules not satisfied.")


class ClearinghouseUnavailable(Exception):
    """A read-only registration check could not reach the clearinghouse."""


def _jsonable(data: dict[str, Any]) -> dict[str, Any]:
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in data.items()}


def _check_owner(claim: Claim, actor: User) -> None:
    if actor.role == Role.SUBMITTER and claim.created_by_id != actor.id:
        raise NotAllowed("You can only act on your own claims.", 403)


def _enqueue_registration(claim: Claim) -> None:
    """Outbox row for the worker. Same transaction as the state change:
    if either write fails, neither happened."""
    Registration.objects.create(claim=claim)


SIDE_EFFECTS = {"submit": _enqueue_registration}


def create_draft(*, created_by: User, payer: str = "", service_date=None, billed_amount: Decimal) -> Claim:
    if created_by.role != Role.SUBMITTER:
        raise NotAllowed("Only submitters create claims.", 403)
    with transaction.atomic():
        claim = Claim.objects.create(
            payer=payer, service_date=service_date, billed_amount=billed_amount, created_by=created_by
        )
        ClaimEvent.objects.create(
            claim=claim, actor=created_by, action="create",
            from_state=State.DRAFT, to_state=State.DRAFT, data={},
        )
    return claim


def update_draft(*, claim: Claim, actor: User, **fields: Any) -> Claim:
    """Edit a draft's payer, service_date or billed_amount. Recorded as an
    `edit` event carrying the changed fields, so the history is complete."""
    allowed = {"payer", "service_date", "billed_amount"}
    unknown = set(fields) - allowed
    if unknown:
        raise NotAllowed(f"Cannot edit {', '.join(sorted(unknown))}.", 400)
    with transaction.atomic():
        claim = Claim.objects.select_for_update().get(pk=claim.pk)
        if claim.created_by_id != actor.id:
            raise NotAllowed("Only the claim's owner can edit it.", 403)
        if claim.state != State.DRAFT:
            raise NotAllowed("Only drafts can be edited.", 400)
        changed = {k: v for k, v in fields.items() if getattr(claim, k) != v}
        if not changed:
            return claim
        for k, v in changed.items():
            setattr(claim, k, v)
        claim.version += 1
        claim.save()
        ClaimEvent.objects.create(
            claim=claim, actor=actor, action="edit",
            from_state=State.DRAFT, to_state=State.DRAFT,
            data=_jsonable({k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in changed.items()}),
        )
    return claim


def transition(*, claim_id: int, action: str, actor: User, expected_version: int, data: dict[str, Any] | None = None) -> Claim:
    data = dict(data or {})
    t = transitions.TRANSITIONS.get(action)
    if t is None:
        raise NotAllowed(f"Unknown action '{action}'.", 400)

    with transaction.atomic():
        # The 409 depends on READ COMMITTED: the losing transaction's SELECT ... FOR UPDATE
        # blocks, then re-reads the committed row and sees version + 1, so the check below
        # fires. Under REPEATABLE READ it would raise a serialization failure instead.
        claim = Claim.objects.select_for_update().get(pk=claim_id)
        _check_owner(claim, actor)
        if claim.version != expected_version:
            raise ConflictError(claim)
        if actor.role != t.role:
            raise NotAllowed(f"Only a {t.role} can {action}.", 403)
        if claim.state not in t.from_states:
            raise NotAllowed(f"Cannot {action} a claim in state {claim.state}.", 400)

        unknown = set(data) - {f.name for f in t.fields}
        if unknown:
            raise RuleViolation({name: "This action does not accept this field." for name in sorted(unknown)})
        errors = t.validate(claim, data, timezone.localdate())
        if errors:
            raise RuleViolation(errors)

        from_state = claim.state
        for name in t.writes:
            setattr(claim, name, data[name])
        claim.state = t.to_state
        claim.version += 1
        claim.save()
        ClaimEvent.objects.create(
            claim=claim, actor=actor, action=action,
            from_state=from_state, to_state=t.to_state, data=_jsonable(data),
        )
        side_effect = SIDE_EFFECTS.get(action)
        if side_effect is not None:
            side_effect(claim)
    return claim


def retry_registration(*, claim: Claim, actor: User) -> Claim:
    """A reviewer asks the worker to try a FAILED registration again.
    HALTED is not retryable here: a human resolves it at the clearinghouse."""
    if actor.role != Role.REVIEWER:
        raise NotAllowed("Only a reviewer can retry a registration.", 403)
    with transaction.atomic():
        claim = Claim.objects.select_for_update().get(pk=claim.pk)
        try:
            reg = Registration.objects.select_for_update().get(claim=claim)
        except Registration.DoesNotExist:
            raise NotAllowed("This claim has no registration to retry.", 400)
        if reg.status != RegistrationStatus.FAILED:
            raise NotAllowed(f"Registration is {reg.status}, not FAILED.", 400)
        reg.status = RegistrationStatus.PENDING
        reg.attempts = 0
        reg.last_error = ""
        reg.next_attempt_at = timezone.now()
        reg.save()
        ClaimEvent.objects.create(
            claim=claim, actor=actor, action="registration_retry_requested", severity=Severity.INFO,
            from_state=claim.state, to_state=claim.state, data={},
        )
    return claim


def reconcile_registration(*, claim: Claim, actor: User, gateway: Gateway) -> Claim:
    """Check an uncertain registration without ever submitting again.

    A zero-result lookup leaves it uncertain: an earlier vendor call may
    still be running. Only a definite rejection is eligible for retry.
    """
    if actor.role != Role.REVIEWER:
        raise NotAllowed("Only a reviewer can reconcile a registration.", 403)
    with transaction.atomic():
        claim = Claim.objects.select_for_update().get(pk=claim.pk)
        try:
            reg = Registration.objects.select_for_update().get(claim=claim)
        except Registration.DoesNotExist:
            raise NotAllowed("This claim has no registration to reconcile.", 400)
        if reg.status != RegistrationStatus.UNCERTAIN:
            raise NotAllowed(f"Registration is {reg.status}, not UNCERTAIN.", 400)
        reference = claim.reference

    try:
        ids = gateway.lookup(reference)
    except Exception as exc:
        log.exception("registration lookup failed claim=%s", reference)
        raise ClearinghouseUnavailable("Could not check the clearinghouse. Try again later.") from exc

    with transaction.atomic():
        claim = Claim.objects.select_for_update().get(pk=claim.pk)
        reg = Registration.objects.select_for_update().get(claim=claim)
        if reg.status != RegistrationStatus.UNCERTAIN:
            return claim  # another check or the original worker resolved it
        if len(ids) > 1:
            reg.status = RegistrationStatus.HALTED
            reg.last_error = f"{len(ids)} submissions found for one reference"
            claim.has_open_alert = True
            action, severity, data = "duplicate_submission", Severity.ALERT, {"submission_ids": ids}
        elif len(ids) == 1:
            reg.status = RegistrationStatus.DONE
            reg.last_error = ""
            claim.submission_id = ids[0]
            action, severity, data = "registration_reconciled", Severity.INFO, {"submission_id": ids[0]}
        else:
            action, severity, data = "registration_checked", Severity.INFO, {"submission_ids_found": 0}
        reg.save()
        claim.save()
        ClaimEvent.objects.create(
            claim=claim, actor=actor, action=action, severity=severity,
            from_state=claim.state, to_state=claim.state, data=data,
        )
    return claim


def acknowledge_alert(*, claim: Claim, actor: User, event_id: int, note: str) -> Claim:
    """Answer an alert on the record. Nothing is cleared; the
    acknowledgement is itself an event, and the claim's flag drops only
    when every alert has one."""
    if actor.role != Role.REVIEWER:
        raise NotAllowed("Only a reviewer can acknowledge an alert.", 403)
    note = (note or "").strip()
    if not note:
        raise RuleViolation({"note": "A note is required."})
    with transaction.atomic():
        claim = Claim.objects.select_for_update().get(pk=claim.pk)
        alert = claim.events.filter(pk=event_id, severity=Severity.ALERT).first()
        if alert is None:
            raise RuleViolation({"event_id": "No such alert on this claim."})
        already = claim.events.filter(action="alert_acknowledged", data__event_id=event_id).exists()
        if already:
            raise RuleViolation({"event_id": "This alert is already acknowledged."})
        ClaimEvent.objects.create(
            claim=claim, actor=actor, action="alert_acknowledged", severity=Severity.INFO,
            from_state=claim.state, to_state=claim.state, data={"event_id": event_id, "note": note},
        )
        open_alerts = claim.events.filter(severity=Severity.ALERT).count()
        acknowledged = claim.events.filter(action="alert_acknowledged").count()
        claim.has_open_alert = acknowledged < open_alerts
        claim.save(update_fields=["has_open_alert", "updated_at"])
    return claim
