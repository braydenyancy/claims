"""Drains the registration outbox (D2, W4, W5).

Four steps, each with its own transaction boundary:

  claim_next  one short transaction: take a due PENDING row, mark it
              IN_FLIGHT with a fresh lease token, commit.
  process     no transaction: look up first, always; adopt a single
              existing ID, halt on several, otherwise register.
  record      one short transaction: write the outcome to the
              registration, the claim, and the event log, but only if
              the lease token still matches.
  reap        one short transaction per stale row: return IN_FLIGHT rows
              whose lease expired to PENDING, locking the claim first.

The vendor is never called while a database transaction is open.

Lock order is Claim before Registration, everywhere — the API's services
lock the claim first, so any path here that took them the other way round
could deadlock against them.
"""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from claims.models import Claim, ClaimEvent, Registration, RegistrationStatus, Severity

from .gateway import Gateway, Outcome, Registered, Unknown

log = logging.getLogger("claims.worker")


def _cfg(key: str):
    return settings.CLEARINGHOUSE[key]


def _event(claim: Claim, action: str, severity: str, data: dict) -> str:
    """Write the event and hand its action back, so the caller can name it
    in the log line without repeating the string."""
    ClaimEvent.objects.create(
        claim=claim, actor=None, action=action, severity=severity,
        from_state=claim.state, to_state=claim.state, data=data,
    )
    return action


def claim_next() -> Registration | None:
    now = timezone.now()
    with transaction.atomic():
        # Lock order: Claim before Registration, everywhere. Claiming work
        # takes no claim lock at all — of=("self",) keeps the select_related
        # join from locking claim rows behind the registration one.
        reg = (
            Registration.objects.select_for_update(skip_locked=True, of=("self",))
            .select_related("claim")
            .filter(status=RegistrationStatus.PENDING, next_attempt_at__lte=now)
            .order_by("next_attempt_at", "id")
            .first()
        )
        if reg is None:
            return None
        reg.status = RegistrationStatus.IN_FLIGHT
        reg.in_flight_since = now
        reg.lease_token = secrets.token_hex(16)
        reg.attempts += 1
        reg.save(update_fields=["status", "in_flight_since", "lease_token", "attempts", "updated_at"])
    return reg


def process(reg: Registration, gateway: Gateway) -> None:
    claim = reg.claim
    ids = gateway.lookup(claim.reference)
    if len(ids) > 1:
        record(reg, None, duplicate_ids=ids)
        return
    if len(ids) == 1:
        record(reg, Registered(ids[0]), reconciled=True)
        return

    outcome = gateway.register(claim.reference, str(claim.billed_amount))
    if isinstance(outcome, Unknown):
        ids = gateway.lookup(claim.reference)
        if len(ids) > 1:
            record(reg, None, duplicate_ids=ids)
            return
        if len(ids) == 1:
            record(reg, Registered(ids[0]), reconciled=True)
            return
    record(reg, outcome)


def record(reg: Registration, outcome: Outcome | None, *, reconciled: bool = False, duplicate_ids: list[str] | None = None) -> None:
    if outcome is None and duplicate_ids is None:
        raise ValueError("record needs an outcome or duplicate ids")
    now = timezone.now()
    with transaction.atomic():
        # Lock order: Claim before Registration, everywhere. services.py takes
        # them in that order too, so neither side can deadlock the other.
        claim = Claim.objects.select_for_update().get(pk=reg.claim_id)
        current = Registration.objects.select_for_update().get(pk=reg.pk)

        if current.lease_token != reg.lease_token or current.status != RegistrationStatus.IN_FLIGHT:
            log.warning("stale result discarded claim=%s outcome=%r", claim.reference, outcome)
            attempt = reg.attempts
            event = _event(claim, "registration_stale_result", Severity.WARNING,
                           {"outcome": repr(outcome), "attempt": attempt})
        else:
            attempt = current.attempts
            if duplicate_ids is not None:
                current.status = RegistrationStatus.HALTED
                current.last_error = f"{len(duplicate_ids)} submissions found for one reference"
                claim.has_open_alert = True
                event = _event(claim, "duplicate_submission", Severity.ALERT,
                               {"submission_ids": duplicate_ids, "attempt": attempt})
            elif isinstance(outcome, Registered):
                current.status = RegistrationStatus.DONE
                current.last_error = ""
                claim.submission_id = outcome.submission_id
                event = _event(claim, "registration_reconciled" if reconciled else "registration_succeeded",
                               Severity.INFO, {"submission_id": outcome.submission_id, "attempt": attempt})
            else:
                current.last_error = outcome.reason[:500]
                if attempt >= _cfg("MAX_ATTEMPTS"):
                    current.status = RegistrationStatus.FAILED
                    claim.has_open_alert = True
                    event = _event(claim, "registration_failed", Severity.ALERT,
                                   {"reason": outcome.reason, "attempts": attempt})
                else:
                    delay = 2 ** attempt
                    current.status = RegistrationStatus.PENDING
                    current.next_attempt_at = now + timedelta(seconds=delay)
                    event = _event(claim, "registration_retry", Severity.WARNING,
                                   {"reason": outcome.reason, "attempt": attempt, "retry_in_seconds": delay})

            current.in_flight_since = None
            current.lease_token = ""
            current.save()
            claim.save()
    log.info("registration claim=%s status=%s attempt=%s event=%s",
             claim.reference, current.status, attempt, event)


def reap() -> int:
    """Return IN_FLIGHT rows whose lease expired to PENDING. Their next
    attempt looks up first, so anything the dead worker actually sent is
    adopted rather than sent again. Lock order: Claim before Registration,
    the same as record()."""
    cutoff = timezone.now() - timedelta(seconds=_cfg("LEASE_SECONDS"))
    candidates = list(
        Registration.objects.filter(status=RegistrationStatus.IN_FLIGHT, in_flight_since__lt=cutoff)
        .values_list("pk", "claim_id")
    )
    recovered = 0
    for reg_pk, claim_pk in candidates:
        with transaction.atomic():
            claim = Claim.objects.select_for_update(skip_locked=True).filter(pk=claim_pk).first()
            if claim is None:
                continue  # a recording worker holds it; next poll
            reg = Registration.objects.select_for_update().get(pk=reg_pk)
            if reg.status != RegistrationStatus.IN_FLIGHT or reg.in_flight_since is None or reg.in_flight_since >= cutoff:
                continue  # already recovered or recorded meanwhile
            attempt = reg.attempts
            reg.status = RegistrationStatus.PENDING
            reg.in_flight_since = None
            reg.lease_token = ""
            reg.next_attempt_at = timezone.now()
            reg.save()
            _event(claim, "registration_recovered", Severity.WARNING, {"attempt": attempt})
            recovered += 1
    if recovered:
        log.warning("reaped %d expired leases", recovered)
    return recovered


def run_once(gateway: Gateway) -> bool:
    """One unit of work. Returns False when nothing was due."""
    reap()
    reg = claim_next()
    if reg is None:
        return False
    process(reg, gateway)
    return True
