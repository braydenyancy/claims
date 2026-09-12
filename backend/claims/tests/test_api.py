"""Requirements 2, 6 and 7 over HTTP: login, scoping, filtering, and the
available-actions list computed server-side. A handful of paths, not the
rule matrix; that lives in test_transitions."""

from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from claims import services
from claims.models import Claim, Role, State, User


@pytest.fixture
def api():
    return APIClient()


def login(api, username):
    response = api.post("/api/auth/login/", {"username": username, "password": "password"}, format="json")
    assert response.status_code == 200, response.content
    return response.json()


@pytest.mark.django_db
def test_login_logout_me(api, submitter):
    assert api.get("/api/me/").status_code == 403
    body = login(api, "sam")
    assert body == {"id": submitter.id, "username": "sam", "role": "submitter"}
    assert api.get("/api/me/").json()["username"] == "sam"
    assert api.post("/api/auth/logout/").status_code == 204
    assert api.get("/api/me/").status_code == 403


@pytest.mark.django_db
def test_login_rejects_bad_password(api, submitter):
    response = api.post("/api/auth/login/", {"username": "sam", "password": "nope"}, format="json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_submitter_creates_draft_and_sees_only_own(api, submitter, reviewer):
    other = User.objects.create_user("other", password="password", role=Role.SUBMITTER)
    services.create_draft(created_by=other, billed_amount=Decimal("5.00"))

    login(api, "sam")
    response = api.post(
        "/api/claims/",
        {"payer": "Acme", "service_date": "2026-09-01", "billed_amount": "100.00"},
        format="json",
    )
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["state"] == "DRAFT" and body["version"] == 0 and body["reference"].startswith("CLM-")

    listed = api.get("/api/claims/").json()["results"]
    assert [c["id"] for c in listed] == [body["id"]]

    other_claim = Claim.objects.get(created_by=other)
    assert api.get(f"/api/claims/{other_claim.id}/").status_code == 404

    api.post("/api/auth/logout/")
    login(api, "rita")
    assert api.get("/api/claims/").json()["count"] == 2


@pytest.mark.django_db
def test_reviewer_cannot_create(api, reviewer):
    login(api, "rita")
    response = api.post("/api/claims/", {"billed_amount": "1.00"}, format="json")
    assert response.status_code == 403


@pytest.mark.django_db
def test_list_filters_by_state(api, submitter):
    services.create_draft(created_by=submitter, billed_amount=Decimal("1.00"))
    submitted = services.create_draft(
        created_by=submitter, payer="Acme", service_date=date(2026, 9, 1), billed_amount=Decimal("2.00")
    )
    services.transition(claim_id=submitted.pk, action="submit", actor=submitter, expected_version=0)

    login(api, "sam")
    assert api.get("/api/claims/?state=SUBMITTED").json()["count"] == 1
    assert api.get("/api/claims/?state=DRAFT").json()["count"] == 1
    assert api.get("/api/claims/").json()["count"] == 2


@pytest.mark.django_db
def test_detail_available_actions_come_from_the_server(api, submitter, reviewer):
    claim = services.create_draft(created_by=submitter, billed_amount=Decimal("1.00"))

    login(api, "sam")
    body = api.get(f"/api/claims/{claim.id}/").json()
    assert [a["action"] for a in body["available_actions"]] == ["submit", "withdraw"]
    assert body["available_actions"][0]["blocked_reason"]  # incomplete draft: rule fails
    assert body["registration"] == {"status": "not_submitted"}

    api.post("/api/auth/logout/")
    login(api, "rita")
    body = api.get(f"/api/claims/{claim.id}/").json()
    assert body["available_actions"] == []


@pytest.mark.django_db
def test_detail_lists_deny_choices(api, submitter, reviewer):
    claim = Claim.objects.create(
        payer="Acme", service_date=date(2026, 9, 1), billed_amount=Decimal("1.00"),
        submission_id="CH-X", state=State.UNDER_REVIEW, created_by=submitter,
    )
    login(api, "rita")
    body = api.get(f"/api/claims/{claim.id}/").json()
    deny = next(a for a in body["available_actions"] if a["action"] == "deny")
    assert deny["fields"] == [{"name": "denial_reason", "type": "choice", "choices": [
        "not_covered", "duplicate", "insufficient_documentation", "out_of_network", "timely_filing",
    ]}]
    assert body["registration"] == {"status": "registered", "submission_id": "CH-X"}


@pytest.mark.django_db
def test_patch_draft_and_history(api, submitter):
    claim = services.create_draft(created_by=submitter, billed_amount=Decimal("1.00"))
    login(api, "sam")
    response = api.patch(f"/api/claims/{claim.id}/", {"payer": "Acme"}, format="json")
    assert response.status_code == 200 and response.json()["payer"] == "Acme"

    history = api.get(f"/api/claims/{claim.id}/history/").json()
    assert [e["action"] for e in history] == ["create", "edit"]
    assert history[1]["data"] == {"payer": "Acme"} and history[1]["actor"] == "sam"

    assert api.delete(f"/api/claims/{claim.id}/history/").status_code == 405
