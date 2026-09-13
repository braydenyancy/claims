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
