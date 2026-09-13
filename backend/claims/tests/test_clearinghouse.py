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
