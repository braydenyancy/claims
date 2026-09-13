# Stage 2: Clearinghouse Registration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A submitted claim is registered with the clearinghouse exactly once by a separate worker process, every outcome is an audit event, and failures and alerts are visible and actionable on the API.

**Architecture:** `submit` enqueues a `Registration` row in the same transaction as the state change (transactional outbox). A worker process claims due rows with `SELECT ... FOR UPDATE SKIP LOCKED`, and, outside any transaction, always calls `lookup` before `submit` so a lost result is adopted rather than re-billed. A gateway class is the only importer of the vendor module and converts its two exceptions into an explicit outcome type. A lease token on each in-flight row makes late results from a dead worker harmless. Alerts are a severity on events plus a flag on the claim.

**Tech Stack:** Same as stage 1. No new dependencies.

**Spec:** `docs/specs/2026-09-12-stage-2-clearinghouse.md` (binding). Decisions D1, D2, D6, D7, D11. Workflows W4, W5, W6.

## Global Constraints

- No new dependencies. `vendor/clearinghouse.py` is never modified. It is imported only inside `backend/claims/clearinghouse/gateway.py`, and only inside `VendorGateway` methods.
- The vendor module is importable as `clearinghouse`: `PYTHONPATH=/app/vendor` in the image; `pythonpath = ["../vendor"]` in pytest config for local runs.
- Never call `register` or `lookup` inside a database transaction.
- Every registration outcome writes exactly one `ClaimEvent` with `actor=None` and the severity the spec's table gives.
- Backoff is `2 ** attempts` seconds. Settings `CLEARINGHOUSE = {GATEWAY, MAX_ATTEMPTS=5, LEASE_SECONDS=60, POLL_SECONDS=1.0}` from the environment.
- Registration statuses: `PENDING`, `IN_FLIGHT`, `DONE`, `FAILED`, `HALTED`. API `registration.status` is the lowercase of these, or `not_submitted` for a claim with no registration row.
- Commit messages: subject + body only. No tool, model, or assistant attribution of any kind.
- Tests: `cd backend && uv run pytest -q` against compose Postgres on host port 5433. Every task ends green with no warnings.
- Seeded logins unchanged: `sam`, `rita`, `rob`, password `password`.

---

### Task 1: Registration model and enqueue on submit

**Files:**
- Modify: `backend/claims/models.py`, `backend/claims/services.py`, `backend/config/settings.py`, `backend/pyproject.toml`
- Create: `backend/claims/migrations/0004_registration.py` (generated)
- Modify: `backend/claims/tests/test_transitions.py`

**Interfaces:**
- Produces: `models.RegistrationStatus`, `models.Registration` (fields `claim`, `status`, `attempts`, `next_attempt_at`, `in_flight_since`, `lease_token`, `last_error`, `created_at`, `updated_at`), `Claim.has_open_alert`, `settings.CLEARINGHOUSE`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/claims/tests/test_transitions.py`:

```python
from unittest.mock import patch

from claims.models import Registration, RegistrationStatus


@pytest.mark.django_db
def test_submit_enqueues_registration_in_the_same_transaction(submitter):
    claim = make_claim(submitter, State.DRAFT, submission_id="")
    services.transition(claim_id=claim.pk, action="submit", actor=submitter, expected_version=0)
    reg = Registration.objects.get(claim=claim)
    assert reg.status == RegistrationStatus.PENDING
    assert reg.attempts == 0
    assert reg.next_attempt_at <= timezone.now()


@pytest.mark.django_db
def test_submit_rolls_back_when_enqueue_fails(submitter):
    claim = make_claim(submitter, State.DRAFT, submission_id="")
    with patch("claims.services.Registration.objects.create", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            services.transition(claim_id=claim.pk, action="submit", actor=submitter, expected_version=0)
    claim.refresh_from_db()
    assert claim.state == State.DRAFT
    assert claim.version == 0
    assert not ClaimEvent.objects.filter(claim=claim).exists()
    assert not Registration.objects.filter(claim=claim).exists()


@pytest.mark.django_db
def test_only_submit_enqueues(submitter, reviewer):
    claim = make_claim(submitter, State.SUBMITTED)
    services.transition(claim_id=claim.pk, action="start_review", actor=reviewer, expected_version=0)
    assert not Registration.objects.filter(claim=claim).exists()
```

Add `from django.utils import timezone` to the test file's imports.

- [ ] **Step 2: Run to verify they fail**

Run from `backend/`: `uv run pytest claims/tests/test_transitions.py -q`. Expected: ImportError on `Registration`.

- [ ] **Step 3: Models**

In `backend/claims/models.py`, add `from django.utils import timezone` to the imports, add `has_open_alert = models.BooleanField(default=False)` to `Claim` after `submission_id`, and append at the end of the file:

```python
class RegistrationStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    IN_FLIGHT = "IN_FLIGHT", "In flight"
    DONE = "DONE", "Done"
    FAILED = "FAILED", "Failed"
    HALTED = "HALTED", "Halted"


class Registration(models.Model):
    """The outbox row for one claim's clearinghouse registration (D2).
    Created with the submit transition, in the same transaction. The
    worker owns every later change. One per claim, ever."""

    claim = models.OneToOneField(Claim, on_delete=models.PROTECT, related_name="registration")
    status = models.CharField(max_length=12, choices=RegistrationStatus.choices, default=RegistrationStatus.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    in_flight_since = models.DateTimeField(null=True, blank=True)
    lease_token = models.CharField(max_length=32, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["status", "next_attempt_at"], name="registration_due_idx")]

    def __str__(self):
        return f"{self.claim_id}:{self.status}"
```

Run `uv run python manage.py makemigrations claims -n registration` and confirm `0004_registration.py` appears. Commit it unedited.

- [ ] **Step 4: Enqueue in the service**

In `backend/claims/services.py`, import `Registration` from `.models`, and add after the `_check_owner` function:

```python
def _enqueue_registration(claim: Claim) -> None:
    """Outbox row for the worker (D2). Same transaction as the state change:
    if either write fails, neither happened."""
    Registration.objects.create(claim=claim)


SIDE_EFFECTS = {"submit": _enqueue_registration}
```

In `transition()`, immediately after the `ClaimEvent.objects.create(...)` call and still inside the `with transaction.atomic():` block, add:

```python
        side_effect = SIDE_EFFECTS.get(action)
        if side_effect is not None:
            side_effect(claim)
```

- [ ] **Step 5: Settings and pytest path**

Append to `backend/config/settings.py`:

```python
CLEARINGHOUSE = {
    "GATEWAY": os.environ.get("CLEARINGHOUSE_GATEWAY", "claims.clearinghouse.gateway.VendorGateway"),
    "MAX_ATTEMPTS": int(os.environ.get("CLEARINGHOUSE_MAX_ATTEMPTS", "5")),
    "LEASE_SECONDS": int(os.environ.get("CLEARINGHOUSE_LEASE_SECONDS", "60")),
    "POLL_SECONDS": float(os.environ.get("CLEARINGHOUSE_POLL_SECONDS", "1.0")),
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "loggers": {"claims": {"handlers": ["console"], "level": "INFO", "propagate": False}},
}
```

In `backend/pyproject.toml` under `[tool.pytest.ini_options]` add `pythonpath = ["../vendor"]`.

- [ ] **Step 6: Run the full suite**

`uv run pytest -q`. Expected: all green. The stage 1 seed test still passes because the seed's submitted claims now also get PENDING rows, which nothing asserts against yet.

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "Add the registration outbox row and enqueue it on submit

Registration is one row per claim with a status, attempt count, next
attempt time, lease fields and last error. The submit transition
creates it inside the same transaction as the state change, so a
failed enqueue rolls the submit back. Claims gain has_open_alert for
the alert lifecycle. Settings carry the worker knobs."
```

---

### Task 2: Gateway with an explicit outcome type

**Files:**
- Create: `backend/claims/clearinghouse/__init__.py`, `backend/claims/clearinghouse/gateway.py`
- Create: `backend/claims/tests/test_clearinghouse.py`

**Interfaces:**
- Produces: `gateway.Registered(submission_id)`, `gateway.Rejected(reason)`, `gateway.Unknown(reason)`, `gateway.Outcome`, `gateway.Gateway` (Protocol with `register(reference, amount) -> Outcome` and `lookup(reference) -> list[str]`), `gateway.VendorGateway`, `gateway.FakeGateway(outcomes=(), record_on_unknown=True)` with `.records`, `.register_calls`, `.lookup_calls`.

- [ ] **Step 1: Write the failing tests**

`backend/claims/tests/test_clearinghouse.py`:

```python
"""Requirement 5: register exactly once against a slow, unreliable
clearinghouse. The gateway tests prove the vendor's two failure modes are
mapped to distinct outcomes and that a timeout really does leave a record
behind, which is the fact the whole worker design rests on."""

from decimal import Decimal

import pytest

from claims.clearinghouse import gateway as gw


@pytest.fixture
def vendor(monkeypatch, tmp_path):
    """The real vendor module with its randomness and sleep pinned and its
    SQLite file pointed at a temp path. The file on disk is untouched."""
    import clearinghouse

    monkeypatch.setattr(clearinghouse, "_DB", tmp_path / "clearinghouse.sqlite3")
    monkeypatch.setattr(clearinghouse.time, "sleep", lambda s: None)
    return clearinghouse


def _roll(monkeypatch, vendor, value):
    monkeypatch.setattr(vendor.random, "random", lambda: value)


def test_vendor_success_is_registered(monkeypatch, vendor):
    _roll(monkeypatch, vendor, 0.9)
    outcome = gw.VendorGateway().register("CLM-A", "10.00")
    assert isinstance(outcome, gw.Registered)
    assert outcome.submission_id.startswith("CH-")
    assert gw.VendorGateway().lookup("CLM-A") == [outcome.submission_id]


def test_vendor_error_is_rejected_and_records_nothing(monkeypatch, vendor):
    _roll(monkeypatch, vendor, 0.05)
    outcome = gw.VendorGateway().register("CLM-B", "10.00")
    assert isinstance(outcome, gw.Rejected)
    assert gw.VendorGateway().lookup("CLM-B") == []


def test_vendor_timeout_is_unknown_but_recorded(monkeypatch, vendor):
    _roll(monkeypatch, vendor, 0.2)
    outcome = gw.VendorGateway().register("CLM-C", "10.00")
    assert isinstance(outcome, gw.Unknown)
    assert len(gw.VendorGateway().lookup("CLM-C")) == 1


def test_fake_mirrors_vendor_recording_rules():
    fake = gw.FakeGateway(outcomes=[gw.Rejected("down"), gw.Unknown("slow"), gw.Registered("CH-1")])
    assert isinstance(fake.register("R", "1.00"), gw.Rejected)
    assert fake.lookup("R") == []
    assert isinstance(fake.register("R", "1.00"), gw.Unknown)
    assert len(fake.lookup("R")) == 1
    assert fake.register("R", "1.00") == gw.Registered("CH-1")
    assert len(fake.lookup("R")) == 2
    assert fake.register_calls == [("R", "1.00")] * 3
    assert fake.lookup_calls == ["R", "R", "R"]


def test_fake_can_lose_a_timeout():
    fake = gw.FakeGateway(outcomes=[gw.Unknown("slow")], record_on_unknown=False)
    fake.register("R", "1.00")
    assert fake.lookup("R") == []
```

- [ ] **Step 2: Run to verify they fail**

`uv run pytest claims/tests/test_clearinghouse.py -q`. Expected: ImportError on `claims.clearinghouse`.

- [ ] **Step 3: Gateway**

`backend/claims/clearinghouse/__init__.py`: empty.

`backend/claims/clearinghouse/gateway.py`:

```python
"""The one door to the clearinghouse (D1).

VendorGateway is the only code that imports the vendor module. It turns
the vendor's two exceptions into explicit outcomes so callers must handle
"maybe recorded" as a value rather than forgetting to catch it.

FakeGateway mirrors the vendor's recording rules for tests: a Registered
outcome records, a Rejected one does not, and an Unknown one records
unless told otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Registered:
    submission_id: str


@dataclass(frozen=True)
class Rejected:
    """The clearinghouse said no. Nothing was recorded. Safe to retry."""

    reason: str


@dataclass(frozen=True)
class Unknown:
    """No answer in time. The submission MAY have been recorded. Never
    retry blind: look up first."""

    reason: str


Outcome = Registered | Rejected | Unknown


class Gateway(Protocol):
    def register(self, reference: str, amount: str) -> Outcome: ...

    def lookup(self, reference: str) -> list[str]: ...


class VendorGateway:
    """Imports the vendor module lazily so the rest of the app never needs
    it on the path."""

    def register(self, reference: str, amount: str) -> Outcome:
        import clearinghouse

        try:
            return Registered(clearinghouse.submit(reference, amount))
        except clearinghouse.ClearinghouseError as exc:
            return Rejected(str(exc))
        except clearinghouse.ClearinghouseTimeout as exc:
            return Unknown(str(exc))

    def lookup(self, reference: str) -> list[str]:
        import clearinghouse

        return clearinghouse.lookup(reference)


class FakeGateway:
    def __init__(self, outcomes: list[Outcome] | tuple[Outcome, ...] = (), record_on_unknown: bool = True):
        self.outcomes = list(outcomes)
        self.record_on_unknown = record_on_unknown
        self.records: dict[str, list[str]] = {}
        self.register_calls: list[tuple[str, str]] = []
        self.lookup_calls: list[str] = []

    def register(self, reference: str, amount: str) -> Outcome:
        self.register_calls.append((reference, amount))
        n = len(self.register_calls)
        outcome = self.outcomes.pop(0) if self.outcomes else Registered(f"CH-FAKE{n:04d}")
        if isinstance(outcome, Registered):
            self.records.setdefault(reference, []).append(outcome.submission_id)
        elif isinstance(outcome, Unknown) and self.record_on_unknown:
            self.records.setdefault(reference, []).append(f"CH-LOST{n:04d}")
        return outcome

    def lookup(self, reference: str) -> list[str]:
        self.lookup_calls.append(reference)
        return list(self.records.get(reference, []))
```

- [ ] **Step 4: Run to verify they pass**

`uv run pytest claims/tests/test_clearinghouse.py -q`. Expected: 5 passed. Then the full suite.

- [ ] **Step 5: Commit**

```bash
git add backend/claims/clearinghouse backend/claims/tests/test_clearinghouse.py
git commit -m "Add the clearinghouse gateway with an explicit outcome type

VendorGateway is the only importer of the vendor module and maps its
two exceptions to Rejected and Unknown so a caller cannot forget that
a timeout may have recorded a submission. FakeGateway mirrors those
recording rules for tests. The vendor tests pin its randomness and
point its SQLite file at a temp path."
```

---

### Task 3: Worker core

**Files:**
- Create: `backend/claims/clearinghouse/worker.py`
- Modify: `backend/claims/tests/test_clearinghouse.py`

**Interfaces:**
- Consumes: `Registration`, `RegistrationStatus`, `Claim`, `ClaimEvent`, `Severity`, gateway types, `settings.CLEARINGHOUSE`.
- Produces: `worker.claim_next() -> Registration | None`, `worker.process(registration, gateway) -> None`, `worker.record(registration, outcome, *, reconciled=False, duplicate_ids=None) -> None`, `worker.run_once(gateway) -> bool` (Task 4 adds `reap`).

- [ ] **Step 1: Write the failing tests**

Append to `backend/claims/tests/test_clearinghouse.py`:

```python
from datetime import timedelta

from django.utils import timezone

from claims import services
from claims.clearinghouse import worker
from claims.models import Claim, ClaimEvent, Registration, RegistrationStatus, State


def submitted(submitter, reference="CLM-TEST0001"):
    """A claim with a PENDING registration, as the submit transition leaves it."""
    claim = Claim.objects.create(
        reference=reference, payer="Acme", service_date=timezone.localdate(),
        billed_amount=Decimal("100.00"), state=State.SUBMITTED, created_by=submitter,
    )
    Registration.objects.create(claim=claim)
    return claim


def events(claim):
    return list(claim.events.filter(actor__isnull=True).values_list("action", "severity"))


@pytest.mark.django_db
def test_claim_next_takes_due_pending_and_marks_in_flight(submitter):
    claim = submitted(submitter)
    reg = worker.claim_next()
    assert reg.claim_id == claim.id
    reg.refresh_from_db()
    assert reg.status == RegistrationStatus.IN_FLIGHT
    assert reg.attempts == 1
    assert reg.in_flight_since is not None
    assert len(reg.lease_token) == 32
    assert worker.claim_next() is None


@pytest.mark.django_db
def test_claim_next_skips_not_yet_due(submitter):
    claim = submitted(submitter)
    Registration.objects.filter(claim=claim).update(next_attempt_at=timezone.now() + timedelta(minutes=5))
    assert worker.claim_next() is None


@pytest.mark.django_db
def test_success_path(submitter):
    claim = submitted(submitter)
    fake = gw.FakeGateway(outcomes=[gw.Registered("CH-OK")])
    assert worker.run_once(fake) is True
    claim.refresh_from_db()
    reg = claim.registration
    assert (reg.status, claim.submission_id) == (RegistrationStatus.DONE, "CH-OK")
    assert fake.lookup_calls == ["CLM-TEST0001"]
    assert fake.register_calls == [("CLM-TEST0001", "100.00")]
    assert events(claim) == [("registration_succeeded", "info")]
    assert reg.in_flight_since is None and reg.lease_token == ""


@pytest.mark.django_db
def test_lookup_runs_before_every_register(submitter):
    claim = submitted(submitter)
    fake = gw.FakeGateway()
    fake.records["CLM-TEST0001"] = ["CH-ALREADY"]
    worker.run_once(fake)
    claim.refresh_from_db()
    assert claim.submission_id == "CH-ALREADY"
    assert fake.register_calls == []
    assert events(claim) == [("registration_reconciled", "info")]


@pytest.mark.django_db
def test_rejected_retries_with_backoff(submitter, settings):
    settings.CLEARINGHOUSE = {**settings.CLEARINGHOUSE, "MAX_ATTEMPTS": 5}
    claim = submitted(submitter)
    fake = gw.FakeGateway(outcomes=[gw.Rejected("Service unavailable")])
    before = timezone.now()
    worker.run_once(fake)
    reg = Registration.objects.get(claim=claim)
    assert reg.status == RegistrationStatus.PENDING
    assert reg.attempts == 1
    assert reg.last_error == "Service unavailable"
    assert timedelta(seconds=1) <= reg.next_attempt_at - before <= timedelta(seconds=3)
    assert events(claim) == [("registration_retry", "warning")]


@pytest.mark.django_db
def test_budget_exhausted_fails_with_alert(submitter, settings):
    settings.CLEARINGHOUSE = {**settings.CLEARINGHOUSE, "MAX_ATTEMPTS": 2}
    claim = submitted(submitter)
    fake = gw.FakeGateway(outcomes=[gw.Rejected("down"), gw.Rejected("down")])
    worker.run_once(fake)
    Registration.objects.filter(claim=claim).update(next_attempt_at=timezone.now())
    worker.run_once(fake)
    claim.refresh_from_db()
    assert claim.registration.status == RegistrationStatus.FAILED
    assert claim.has_open_alert is True
    assert events(claim) == [("registration_retry", "warning"), ("registration_failed", "alert")]


@pytest.mark.django_db
def test_unknown_with_record_is_adopted(submitter):
    claim = submitted(submitter)
    fake = gw.FakeGateway(outcomes=[gw.Unknown("No response")])
    worker.run_once(fake)
    claim.refresh_from_db()
    assert claim.registration.status == RegistrationStatus.DONE
    assert claim.submission_id == "CH-LOST0001"
    assert fake.register_calls == [("CLM-TEST0001", "100.00")]
    assert fake.lookup_calls == ["CLM-TEST0001", "CLM-TEST0001"]
    assert events(claim) == [("registration_reconciled", "info")]


@pytest.mark.django_db
def test_unknown_without_record_retries(submitter):
    claim = submitted(submitter)
    fake = gw.FakeGateway(outcomes=[gw.Unknown("No response")], record_on_unknown=False)
    worker.run_once(fake)
    reg = Registration.objects.get(claim=claim)
    assert reg.status == RegistrationStatus.PENDING
    assert events(claim) == [("registration_retry", "warning")]


@pytest.mark.django_db
def test_duplicate_records_halt_with_alert(submitter):
    claim = submitted(submitter)
    fake = gw.FakeGateway()
    fake.records["CLM-TEST0001"] = ["CH-1", "CH-2"]
    worker.run_once(fake)
    claim.refresh_from_db()
    assert claim.registration.status == RegistrationStatus.HALTED
    assert claim.submission_id == ""
    assert claim.has_open_alert is True
    assert fake.register_calls == []
    event = claim.events.get(action="duplicate_submission")
    assert event.severity == "alert" and event.data["submission_ids"] == ["CH-1", "CH-2"]


@pytest.mark.django_db
def test_crashed_worker_result_is_adopted_not_resubmitted(submitter):
    """Worker A registered successfully and died before recording. Worker B
    must adopt A's ID, not create a second billed submission."""
    claim = submitted(submitter)
    fake = gw.FakeGateway(outcomes=[gw.Registered("CH-FROM-A")])
    fake.register("CLM-TEST0001", "100.00")  # A's call, result lost
    worker.run_once(fake)
    claim.refresh_from_db()
    assert claim.submission_id == "CH-FROM-A"
    assert len(fake.register_calls) == 1
    assert fake.lookup("CLM-TEST0001") == ["CH-FROM-A"]


@pytest.mark.django_db
def test_stale_lease_result_is_discarded(submitter):
    """A slow worker whose lease was reaped and re-claimed must not overwrite
    the newer attempt's result."""
    claim = submitted(submitter)
    stale = worker.claim_next()
    Registration.objects.filter(pk=stale.pk).update(
        status=RegistrationStatus.DONE, lease_token="newer-token", in_flight_since=None
    )
    Claim.objects.filter(pk=claim.pk).update(submission_id="CH-NEWER")
    worker.record(stale, gw.Registered("CH-STALE"))
    claim.refresh_from_db()
    assert claim.submission_id == "CH-NEWER"
    assert claim.registration.status == RegistrationStatus.DONE
    assert events(claim) == [("registration_stale_result", "warning")]


@pytest.mark.django_db(transaction=True)
def test_two_workers_claim_different_rows(submitter):
    import threading
    from django.db import connection

    a = submitted(submitter, "CLM-A")
    b = submitted(submitter, "CLM-B")
    taken = []
    barrier = threading.Barrier(2)

    def take():
        try:
            barrier.wait(timeout=5)
            reg = worker.claim_next()
            taken.append(reg.claim_id if reg else None)
        finally:
            connection.close()

    threads = [threading.Thread(target=take) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert sorted(taken) == sorted([a.id, b.id])
```

- [ ] **Step 2: Run to verify they fail**

`uv run pytest claims/tests/test_clearinghouse.py -q`. Expected: ImportError on `worker`.

- [ ] **Step 3: Worker**

`backend/claims/clearinghouse/worker.py`:

```python
"""Drains the registration outbox (D2, W4, W5).

Three steps, each with its own transaction boundary:

  claim_next  one short transaction: take a due PENDING row, mark it
              IN_FLIGHT with a fresh lease token, commit.
  process     no transaction: look up first, always; adopt a single
              existing ID, halt on several, otherwise register.
  record      one short transaction: write the outcome to the
              registration, the claim, and the event log, but only if
              the lease token still matches.

The vendor is never called while a database transaction is open.
"""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from claims.models import Claim, ClaimEvent, Registration, RegistrationStatus, Severity

from .gateway import Gateway, Outcome, Registered, Rejected, Unknown

log = logging.getLogger("claims.worker")


def _cfg(key: str):
    return settings.CLEARINGHOUSE[key]


def _event(claim: Claim, action: str, severity: str, data: dict) -> None:
    ClaimEvent.objects.create(
        claim=claim, actor=None, action=action, severity=severity,
        from_state=claim.state, to_state=claim.state, data=data,
    )


def claim_next() -> Registration | None:
    now = timezone.now()
    with transaction.atomic():
        reg = (
            Registration.objects.select_for_update(skip_locked=True)
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
    now = timezone.now()
    with transaction.atomic():
        current = Registration.objects.select_for_update().get(pk=reg.pk)
        claim = Claim.objects.select_for_update().get(pk=current.claim_id)

        if current.lease_token != reg.lease_token or current.status != RegistrationStatus.IN_FLIGHT:
            log.warning("stale result discarded claim=%s outcome=%r", claim.reference, outcome)
            _event(claim, "registration_stale_result", Severity.WARNING,
                   {"outcome": repr(outcome), "attempt": reg.attempts})
            return

        attempt = current.attempts
        if duplicate_ids is not None:
            current.status = RegistrationStatus.HALTED
            current.last_error = f"{len(duplicate_ids)} submissions found for one reference"
            claim.has_open_alert = True
            _event(claim, "duplicate_submission", Severity.ALERT,
                   {"submission_ids": duplicate_ids, "attempt": attempt})
        elif isinstance(outcome, Registered):
            current.status = RegistrationStatus.DONE
            current.last_error = ""
            claim.submission_id = outcome.submission_id
            _event(claim, "registration_reconciled" if reconciled else "registration_succeeded",
                   Severity.INFO, {"submission_id": outcome.submission_id, "attempt": attempt})
        else:
            current.last_error = outcome.reason[:500]
            if attempt >= _cfg("MAX_ATTEMPTS"):
                current.status = RegistrationStatus.FAILED
                claim.has_open_alert = True
                _event(claim, "registration_failed", Severity.ALERT,
                       {"reason": outcome.reason, "attempts": attempt})
            else:
                delay = 2 ** attempt
                current.status = RegistrationStatus.PENDING
                current.next_attempt_at = now + timedelta(seconds=delay)
                _event(claim, "registration_retry", Severity.WARNING,
                       {"reason": outcome.reason, "attempt": attempt, "retry_in_seconds": delay})

        current.in_flight_since = None
        current.lease_token = ""
        current.save()
        claim.save()
    log.info("registration claim=%s status=%s attempt=%s", claim.reference, current.status, attempt)


def run_once(gateway: Gateway) -> bool:
    """One unit of work. Returns False when nothing was due."""
    reg = claim_next()
    if reg is None:
        return False
    process(reg, gateway)
    return True
```

- [ ] **Step 4: Run to verify they pass**

`uv run pytest claims/tests/test_clearinghouse.py -q` then the full suite. Expected: green, no warnings. If `test_two_workers_claim_different_rows` is flaky, report DONE_WITH_CONCERNS with the output; do not loosen it.

- [ ] **Step 5: Commit**

```bash
git add backend/claims/clearinghouse/worker.py backend/claims/tests/test_clearinghouse.py
git commit -m "Add the registration worker core

claim_next takes one due row under SKIP LOCKED and leases it. process
looks up before it ever registers, adopts a single existing ID, halts
on several, and on a timeout looks up again before scheduling a retry.
record writes the outcome, the claim, and the audit event in one
transaction, and discards results whose lease is no longer current."
```

---

### Task 4: Reaper, run_worker command, compose service, seed

**Files:**
- Modify: `backend/claims/clearinghouse/worker.py`, `backend/claims/tests/test_clearinghouse.py`
- Create: `backend/claims/management/commands/run_worker.py`
- Modify: `backend/claims/management/commands/seed.py`, `backend/claims/tests/test_seed.py`, `compose.yaml`, `README.md`

**Interfaces:**
- Produces: `worker.reap() -> int`; `run_once` now calls `reap()` first; `manage.py run_worker [--once]`; compose `worker` service.

- [ ] **Step 1: Write the failing tests**

Append to `backend/claims/tests/test_clearinghouse.py`:

```python
@pytest.mark.django_db
def test_reap_returns_expired_leases_to_pending(submitter, settings):
    settings.CLEARINGHOUSE = {**settings.CLEARINGHOUSE, "LEASE_SECONDS": 60}
    claim = submitted(submitter)
    reg = worker.claim_next()
    Registration.objects.filter(pk=reg.pk).update(in_flight_since=timezone.now() - timedelta(seconds=61))
    assert worker.reap() == 1
    reg.refresh_from_db()
    assert reg.status == RegistrationStatus.PENDING
    assert reg.lease_token == "" and reg.in_flight_since is None
    assert events(claim) == [("registration_recovered", "warning")]
    assert worker.reap() == 0


@pytest.mark.django_db
def test_reap_leaves_live_leases_alone(submitter):
    submitted(submitter)
    worker.claim_next()
    assert worker.reap() == 0


@pytest.mark.django_db
def test_run_worker_once_processes_one_row(submitter, settings):
    settings.CLEARINGHOUSE = {**settings.CLEARINGHOUSE, "GATEWAY": "claims.clearinghouse.gateway.FakeGateway"}
    from django.core.management import call_command

    claim = submitted(submitter)
    call_command("run_worker", "--once")
    claim.refresh_from_db()
    assert claim.registration.status == RegistrationStatus.DONE
    assert claim.submission_id.startswith("CH-FAKE")
```

Replace `backend/claims/tests/test_seed.py`'s first test assertions to expect 10 claims and registration rows:

```python
@pytest.mark.django_db
def test_seed_creates_users_and_claims_once():
    call_command("seed")
    call_command("seed")
    assert sorted(User.objects.values_list("username", flat=True)) == ["rita", "rob", "sam"]
    assert set(Claim.objects.values_list("state", flat=True)) == set(State.values)
    assert Claim.objects.count() == 10
    assert ClaimEvent.objects.filter(action="create").count() == 10
    assert User.objects.get(username="sam").check_password("password")
    statuses = sorted(Registration.objects.values_list("status", flat=True))
    assert statuses == ["DONE"] * 5 + ["FAILED", "PENDING"]
    assert Claim.objects.filter(has_open_alert=True).count() == 1
```

Add `Registration` to that file's model import, and in the all-or-nothing test change the two `== 9` to `== 10`.

- [ ] **Step 2: Run to verify they fail**

`uv run pytest claims/tests/test_clearinghouse.py claims/tests/test_seed.py -q`. Expected: AttributeError on `worker.reap`, unknown command, seed count mismatch.

- [ ] **Step 3: Reaper and run_once**

In `backend/claims/clearinghouse/worker.py`, add before `run_once`:

```python
def reap() -> int:
    """Return IN_FLIGHT rows whose lease expired to PENDING. Their next
    attempt looks up first, so anything the dead worker actually sent is
    adopted rather than sent again."""
    cutoff = timezone.now() - timedelta(seconds=_cfg("LEASE_SECONDS"))
    recovered = 0
    with transaction.atomic():
        stale = (
            Registration.objects.select_for_update(skip_locked=True)
            .filter(status=RegistrationStatus.IN_FLIGHT, in_flight_since__lt=cutoff)
            .select_related("claim")
        )
        for reg in stale:
            reg.status = RegistrationStatus.PENDING
            reg.in_flight_since = None
            reg.lease_token = ""
            reg.next_attempt_at = timezone.now()
            reg.save()
            _event(reg.claim, "registration_recovered", Severity.WARNING, {"attempt": reg.attempts})
            recovered += 1
    if recovered:
        log.warning("reaped %d expired leases", recovered)
    return recovered
```

And change `run_once` to call `reap()` as its first line.

- [ ] **Step 4: The command**

`backend/claims/management/commands/run_worker.py`:

```python
"""The registration worker process. Same image as the API, different
command. Run more than one for throughput; SKIP LOCKED keeps them from
taking the same row."""

import signal
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.module_loading import import_string

from claims.clearinghouse import worker


class Command(BaseCommand):
    help = "Drain the clearinghouse registration outbox"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="process at most one row, then exit")

    def handle(self, *args, once=False, **options):
        gateway = import_string(settings.CLEARINGHOUSE["GATEWAY"])()
        stop = {"now": False}

        def _stop(signum, frame):
            stop["now"] = True

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)

        self.stdout.write(f"worker: gateway={type(gateway).__name__} poll={settings.CLEARINGHOUSE['POLL_SECONDS']}s")
        while not stop["now"]:
            worked = worker.run_once(gateway)
            if once:
                return
            if not worked:
                time.sleep(settings.CLEARINGHOUSE["POLL_SECONDS"])
        self.stdout.write("worker: stopped")
```

- [ ] **Step 5: Seed**

In `backend/claims/management/commands/seed.py`, replace the `registered` helper and the module constant with:

```python
def registered(claim, n):
    """Stage 1 stamped an ID directly. Now the seed records a completed
    registration the way the worker would, so the history is honest."""
    sid = f"CH-SEED{n:04d}"
    Registration.objects.filter(claim=claim).update(status=RegistrationStatus.DONE)
    Claim.objects.filter(pk=claim.pk).update(submission_id=sid)
    ClaimEvent.objects.create(
        claim=claim, actor=None, action="registration_succeeded", severity=Severity.INFO,
        from_state=claim.state, to_state=claim.state, data={"submission_id": sid, "attempt": 1},
    )
    claim.refresh_from_db()
    return claim


def failed(claim):
    Registration.objects.filter(claim=claim).update(
        status=RegistrationStatus.FAILED, attempts=5, last_error="Service unavailable"
    )
    Claim.objects.filter(pk=claim.pk).update(has_open_alert=True)
    ClaimEvent.objects.create(
        claim=claim, actor=None, action="registration_failed", severity=Severity.ALERT,
        from_state=claim.state, to_state=claim.state, data={"reason": "Service unavailable", "attempts": 5},
    )
    claim.refresh_from_db()
    return claim
```

Update the imports to include `ClaimEvent`, `Registration`, `RegistrationStatus`, `Severity`. Number the five `registered(...)` calls 1 to 5 in order. After the WITHDRAWN claim, add a tenth claim:

```python
        failed(step(draft("Cascade Care", 10, "510.00"), "submit", sam))  # SUBMITTED, registration failed, open alert
```

Keep the one plain `step(draft(...), "submit", sam)` claim as is: its PENDING row is what the worker registers on boot.

- [ ] **Step 6: Compose and README**

In `compose.yaml`, add a healthcheck to `api`:

```yaml
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health/')"]
      interval: 3s
      timeout: 3s
      retries: 20
```

and add the service:

```yaml
  worker:
    build:
      context: .
      dockerfile: backend/Dockerfile
    entrypoint: ["python", "manage.py", "run_worker"]
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_PORT: "5432"
      POSTGRES_DB: claims
      POSTGRES_USER: claims
      POSTGRES_PASSWORD: claims
    volumes:
      - ./backend:/app
      - ./vendor:/app/vendor
    depends_on:
      api:
        condition: service_healthy
```

The worker bypasses the entrypoint so only the API migrates and seeds; it waits for the API to be healthy so the schema exists.

In `README.md` under "Run", add: `The worker registers submitted claims with the clearinghouse; its log shows every attempt. Knobs: CLEARINGHOUSE_MAX_ATTEMPTS, CLEARINGHOUSE_LEASE_SECONDS, CLEARINGHOUSE_POLL_SECONDS.` Under "Layout", add `- \`vendor/clearinghouse.sqlite3\` is the clearinghouse's own store, created at runtime and git-ignored`.

- [ ] **Step 7: Verify**

`uv run pytest -q` green. Then from the repo root: `docker compose down -v; docker compose up --build -d`, wait, `docker compose logs worker | tail -20`. Expected: a `worker: gateway=VendorGateway` line and, within a few seconds, a `registration claim=CLM-... status=DONE` or `status=PENDING` line for the seeded pending claim. Then `docker compose down` and `docker compose up -d postgres`.

- [ ] **Step 8: Commit**

```bash
git add backend compose.yaml README.md
git commit -m "Add the reaper, the run_worker command, and the worker service

reap returns expired leases to pending so a dead worker's row is
retried, with lookup first. run_worker drains the outbox in a loop,
stops on SIGTERM, and takes --once for tests. Compose runs it as a
second service on the same image, waiting for the API to be healthy so
only the API migrates and seeds. The seed now records real
registrations, one left pending for the worker and one failed with an
open alert."
```

---

### Task 5: Registration and alerts on the API

**Files:**
- Modify: `backend/claims/services.py`, `backend/claims/api/serializers.py`, `backend/claims/api/views.py`
- Modify: `backend/claims/tests/test_api.py`

**Interfaces:**
- Produces: `services.retry_registration(*, claim, actor) -> Claim`, `services.acknowledge_alert(*, claim, actor, event_id, note) -> ClaimEvent`; API `registration` block, `has_open_alert` on list and detail, `?alert=open`, `POST /api/claims/{id}/registration/retry/`, `POST /api/claims/{id}/acknowledge/`.

- [ ] **Step 1: Write the failing tests**

In `backend/claims/tests/test_api.py`, update the two existing registration assertions: in `test_detail_available_actions_come_from_the_server` keep `{"status": "not_submitted"}`; in `test_detail_lists_deny_choices` the claim is created directly without a registration row, so change that assertion to `assert body["registration"] == {"status": "not_submitted"}` (a directly-created claim has no outbox row). Then append:

```python
from claims.models import ClaimEvent, Registration, RegistrationStatus, Severity


def failed_registration(submitter):
    claim = Claim.objects.create(
        payer="Acme", service_date=date(2026, 9, 1), billed_amount=Decimal("1.00"),
        state=State.SUBMITTED, created_by=submitter, has_open_alert=True,
    )
    Registration.objects.create(claim=claim, status=RegistrationStatus.FAILED, attempts=5, last_error="down")
    alert = ClaimEvent.objects.create(
        claim=claim, actor=None, action="registration_failed", severity=Severity.ALERT,
        from_state=State.SUBMITTED, to_state=State.SUBMITTED, data={"reason": "down", "attempts": 5},
    )
    return claim, alert


@pytest.mark.django_db
def test_registration_block_and_alert_flag(api, submitter, reviewer):
    claim, _ = failed_registration(submitter)
    login(api, "rita")
    body = api.get(f"/api/claims/{claim.id}/").json()
    assert body["registration"] == {
        "status": "failed", "attempts": 5, "last_error": "down",
        "submission_id": "", "next_attempt_at": body["registration"]["next_attempt_at"],
    }
    assert body["has_open_alert"] is True
    listed = api.get("/api/claims/?alert=open").json()
    assert [c["id"] for c in listed["results"]] == [claim.id]
    assert listed["results"][0]["has_open_alert"] is True
    assert api.get("/api/claims/?alert=bogus").status_code == 400


@pytest.mark.django_db
def test_retry_failed_registration(api, submitter, reviewer):
    claim, _ = failed_registration(submitter)
    login(api, "rita")
    response = api.post(f"/api/claims/{claim.id}/registration/retry/")
    assert response.status_code == 200, response.content
    assert response.json()["registration"]["status"] == "pending"
    reg = Registration.objects.get(claim=claim)
    assert (reg.attempts, reg.last_error) == (0, "")
    event = claim.events.get(action="registration_retry_requested")
    assert event.actor == reviewer and event.severity == "info"

    again = api.post(f"/api/claims/{claim.id}/registration/retry/")
    assert again.status_code == 400 and "errors" in again.json()


@pytest.mark.django_db
def test_retry_is_reviewer_only_and_scoped(api, submitter, reviewer):
    claim, _ = failed_registration(submitter)
    login(api, "sam")
    assert api.post(f"/api/claims/{claim.id}/registration/retry/").status_code == 403


@pytest.mark.django_db
def test_acknowledge_alert_requires_note_and_clears_flag(api, submitter, reviewer):
    claim, alert = failed_registration(submitter)
    login(api, "rita")
    url = f"/api/claims/{claim.id}/acknowledge/"
    missing = api.post(url, {"event_id": alert.id, "note": "  "}, format="json")
    assert missing.status_code == 400 and "note" in missing.json()["errors"]

    ok = api.post(url, {"event_id": alert.id, "note": "Called the clearinghouse; resubmitting tomorrow."}, format="json")
    assert ok.status_code == 200, ok.content
    assert ok.json()["has_open_alert"] is False
    ack = claim.events.get(action="alert_acknowledged")
    assert ack.actor == reviewer and ack.data == {"event_id": alert.id, "note": "Called the clearinghouse; resubmitting tomorrow."}

    twice = api.post(url, {"event_id": alert.id, "note": "again"}, format="json")
    assert twice.status_code == 400

    other_claim = services.create_draft(created_by=submitter, billed_amount=Decimal("1.00"))
    wrong = api.post(f"/api/claims/{other_claim.id}/acknowledge/", {"event_id": alert.id, "note": "x"}, format="json")
    assert wrong.status_code == 400


@pytest.mark.django_db
def test_acknowledge_is_reviewer_only(api, submitter, reviewer):
    claim, alert = failed_registration(submitter)
    login(api, "sam")
    assert api.post(f"/api/claims/{claim.id}/acknowledge/", {"event_id": alert.id, "note": "x"}, format="json").status_code == 403
```

Also update `test_seed.py` if it asserts nothing about the API; it does not. Update the stage 1 test in `test_api.py` named `test_detail_lists_deny_choices` as described above.

- [ ] **Step 2: Run to verify they fail**

`uv run pytest claims/tests/test_api.py -q`. Expected: the registration shape assertions and 404s on the new routes.

- [ ] **Step 3: Services**

Append to `backend/claims/services.py` (import `Registration`, `RegistrationStatus`, `Severity` from `.models`):

```python
def retry_registration(*, claim: Claim, actor: User) -> Claim:
    """A reviewer asks the worker to try a FAILED registration again.
    HALTED is not retryable here: a human resolves it at the clearinghouse."""
    if actor.role != Role.REVIEWER:
        raise NotAllowed("Only a reviewer can retry a registration.", 403)
    with transaction.atomic():
        claim = Claim.objects.select_for_update().get(pk=claim.pk)
        reg = Registration.objects.select_for_update().get(claim=claim)
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


def acknowledge_alert(*, claim: Claim, actor: User, event_id: int, note: str) -> Claim:
    """Answer an alert on the record (D11, W6). Nothing is cleared; the
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
```

- [ ] **Step 4: Serializers**

In `backend/claims/api/serializers.py`: add `"has_open_alert"` to `ClaimListSerializer.Meta.fields` (after `"version"`); replace `get_registration` with:

```python
    def get_registration(self, claim):
        reg = getattr(claim, "registration", None)
        if reg is None:
            return {"status": "not_submitted"}
        return {
            "status": reg.status.lower(),
            "attempts": reg.attempts,
            "last_error": reg.last_error,
            "submission_id": claim.submission_id,
            "next_attempt_at": reg.next_attempt_at.isoformat() if reg.status == "PENDING" else None,
        }
```

Note `getattr(claim, "registration", None)` raises `RelatedObjectDoesNotExist`, not `AttributeError`, in some Django versions; use this instead:

```python
        try:
            reg = claim.registration
        except Registration.DoesNotExist:
            return {"status": "not_submitted"}
```

with `Registration` imported from `claims.models`. Append:

```python
class AcknowledgeSerializer(serializers.Serializer):
    event_id = serializers.IntegerField(min_value=1)
    note = serializers.CharField(allow_blank=True, trim_whitespace=False)
```

- [ ] **Step 5: Views**

In `backend/claims/api/views.py`: import `AcknowledgeSerializer`; in `get_queryset` after the state filter (still inside `if self.action == "list":`), add:

```python
            alert = self.request.query_params.get("alert")
            if alert:
                if alert != "open":
                    raise ValidationError({"alert": "Only 'open' is supported."})
                qs = qs.filter(has_open_alert=True)
```

Also change the `select_related("created_by")` to `select_related("created_by", "registration")`. Add two actions after `transition`:

```python
    @action(detail=True, methods=["post"], url_path="registration/retry")
    def retry_registration(self, request, pk=None):
        claim = self.get_object()
        try:
            claim = services.retry_registration(claim=claim, actor=request.user)
        except services.NotAllowed as exc:
            return Response({"detail": str(exc), "errors": {}}, status=exc.status_code)
        return self._detail(claim)

    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        claim = self.get_object()
        serializer = AcknowledgeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"detail": "Invalid request.", "errors": {k: " ".join(str(m) for m in v) for k, v in serializer.errors.items()}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            claim = services.acknowledge_alert(claim=claim, actor=request.user, **serializer.validated_data)
        except services.RuleViolation as exc:
            return Response({"detail": str(exc), "errors": exc.errors}, status=status.HTTP_400_BAD_REQUEST)
        except services.NotAllowed as exc:
            return Response({"detail": str(exc), "errors": {}}, status=exc.status_code)
        return self._detail(claim)
```

- [ ] **Step 6: Run the full suite**

`uv run pytest -q`. Expected: green, no warnings. The `_detail` helper re-reads `claim.registration` through the one-to-one; since `retry_registration` returns the locked instance, refresh with `claim.refresh_from_db()` inside the service before returning if the serializer shows a stale status.

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "Expose registration state and the alert lifecycle on the API

The detail payload carries the registration status, attempt count,
last error and next attempt time. Reviewers can retry a failed
registration and acknowledge an alert with a required note; both are
events. The list gains has_open_alert and an alert=open filter."
```

---

### Task 6: Close stage 2

**Files:**
- Modify: `NOTES.md`, `docs/specs/2026-09-12-stage-2-clearinghouse.md`, `docs/architecture/WORKFLOWS.md`, `docs/compliance/COMPLIANCE_PROGRAM.md`
- Create: `docs/receipts/stage-2/README.md`

- [ ] **Step 1: NOTES.md**

Append a `## Stage 2: clearinghouse registration` section, about 200 words, covering: the always-lookup-first rule and why it subsumes the timeout, crash and double-run cases; the three transaction boundaries and that the vendor is never called inside one; the lease token; the alert lifecycle with a required note; what HALTED means and why it is not retryable; the four failure-injection tests (rejected, unknown recorded, unknown lost, duplicate); what is deliberately deferred (Celery as the production swap, real backoff jitter, per-claim idempotency at the vendor if it ever offers one, TRUNCATE guard by database role, history pagination). One sentence on AI use consistent with stage 1.

- [ ] **Step 2: Receipts**

`docs/receipts/stage-2/README.md`: `docker compose down -v && docker compose up --build -d`; `docker compose logs worker` showing the seeded pending claim being registered; then a curl session creating and submitting five claims as `sam`, followed by `docker compose logs worker | grep registration` showing their attempts. With the vendor's 25% failure rate, five claims very likely show at least one `status=PENDING` retry or a `registration_reconciled` event; if not, submit five more and say so. Finish with `GET /api/claims/{id}/history/` for one claim that retried, and the seeded failed claim's `registration/retry/` and `acknowledge/` calls. Then `docker compose down` and `docker compose up -d postgres`.

- [ ] **Step 3: Docs**

Spec: `Status: complete.`, all cuts `- [x]`. In `WORKFLOWS.md` W4, insert `→ lookup(reference) (none found)` between `worker claims row ...` and `gateway.submit`; in W5, prefix with a line `every attempt: lookup first → 1 id: adopt · >1: HALTED · 0: register`; add to W5 `stale lease result → discarded → event(warning, registration_stale_result)`. In `COMPLIANCE_PROGRAM.md` section 6 replace the placeholder with two sentences pointing at the event table, severities, and the worker log; section 7 replace the placeholder with two sentences pointing at the alert lifecycle (W6): alerts are answered with a note on the record, never cleared, and HALTED registrations require human resolution at the clearinghouse before acknowledgement.

- [ ] **Step 4: Commit**

```bash
git add NOTES.md docs
git commit -m "Close stage 2: notes, receipts, workflows, compliance pointers

NOTES.md records the stage 2 design and what is deferred. Receipts
show the worker registering seeded and freshly submitted claims under
compose, a retry, and the alert lifecycle over the API. W4 and W5 gain
the lookup-first step and the stale-lease exit. Compliance program
sections 6 and 7 now point at the mechanisms that exist."
```
