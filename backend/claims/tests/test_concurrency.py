"""Requirement 4: two reviewers act at once, exactly one succeeds.
The thread test is the real race under a row lock; the API test is the
stale screen, which is the common case in practice."""

import threading
from datetime import date
from decimal import Decimal

import pytest
from django.db import connection
from rest_framework.test import APIClient

from claims import services
from claims.models import Claim, ClaimEvent, State


def under_review(submitter):
    return Claim.objects.create(
        payer="Acme", service_date=date(2026, 9, 1), billed_amount=Decimal("100.00"),
        submission_id="CH-X", state=State.UNDER_REVIEW, created_by=submitter,
    )


@pytest.mark.django_db(transaction=True)
def test_two_reviewers_exactly_one_wins(submitter, reviewer, reviewer2):
    claim = under_review(submitter)
    barrier = threading.Barrier(2)
    outcomes = {}

    def act(name, actor, action, data):
        try:
            barrier.wait(timeout=5)
            services.transition(
                claim_id=claim.pk, action=action, actor=actor, expected_version=0, data=data
            )
            outcomes[name] = "ok"
        except services.ConflictError:
            outcomes[name] = "conflict"
        finally:
            connection.close()

    threads = [
        threading.Thread(target=act, args=("rita", reviewer, "approve", {"approved_amount": Decimal("90.00")})),
        threading.Thread(target=act, args=("rob", reviewer2, "deny", {"denial_reason": "duplicate"})),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert sorted(outcomes.values()) == ["conflict", "ok"]
    claim.refresh_from_db()
    assert claim.version == 1
    assert claim.state in (State.APPROVED, State.DENIED)
    assert ClaimEvent.objects.filter(claim=claim, action__in=["approve", "deny"]).count() == 1


@pytest.mark.django_db
def test_stale_screen_gets_409_with_what_happened(submitter, reviewer, reviewer2):
    claim = under_review(submitter)
    rita, rob = APIClient(), APIClient()
    rita.force_login(reviewer)
    rob.force_login(reviewer2)

    ok = rita.post(
        f"/api/claims/{claim.id}/transition/",
        {"action": "approve", "version": 0, "data": {"approved_amount": "90.00"}},
        format="json",
    )
    assert ok.status_code == 200, ok.content
    assert ok.json()["state"] == "APPROVED" and ok.json()["version"] == 1

    stale = rob.post(
        f"/api/claims/{claim.id}/transition/",
        {"action": "deny", "version": 0, "data": {"denial_reason": "duplicate"}},
        format="json",
    )
    assert stale.status_code == 409
    body = stale.json()
    assert body["current_state"] == "APPROVED" and body["current_version"] == 1
    assert body["last_event"]["action"] == "approve" and body["last_event"]["actor"] == "rita"
    assert "detail" in body


@pytest.mark.django_db
def test_conflict_names_the_version_change_not_a_later_system_event(submitter, reviewer, reviewer2):
    claim = under_review(submitter)
    rita, rob = APIClient(), APIClient()
    rita.force_login(reviewer)
    rob.force_login(reviewer2)
    result = rita.post(
        f"/api/claims/{claim.id}/transition/",
        {"action": "approve", "version": 0, "data": {"approved_amount": "90.00"}},
        format="json",
    )
    assert result.status_code == 200
    ClaimEvent.objects.create(
        claim=claim, actor=None, action="registration_checked",
        from_state=State.APPROVED, to_state=State.APPROVED, data={},
    )
    stale = rob.post(
        f"/api/claims/{claim.id}/transition/",
        {"action": "deny", "version": 0, "data": {"denial_reason": "duplicate"}},
        format="json",
    )
    assert stale.status_code == 409
    assert stale.json()["last_event"]["action"] == "approve"
