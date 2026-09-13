"""Requirements 2, 6 and 7 over HTTP: login, scoping, filtering, and the
available-actions list computed server-side. A handful of paths, not the
rule matrix; that lives in test_transitions."""

from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from claims import services
from claims.models import Claim, ClaimEvent, Registration, RegistrationStatus, Role, Severity, State, User


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
    assert body == {"id": submitter.id, "username": "sam", "role": "submitter", "can_create_claims": True}
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
    assert body["registration"] == {"status": "not_submitted"}


@pytest.mark.django_db
def test_patch_refused_for_non_owner(api, submitter, reviewer):
    claim = services.create_draft(created_by=submitter, payer="Acme", billed_amount=Decimal("1.00"))
    login(api, "rita")
    response = api.patch(f"/api/claims/{claim.id}/", {"payer": "Changed"}, format="json")
    assert response.status_code == 403
    claim.refresh_from_db()
    assert claim.payer == "Acme"
    assert not claim.events.filter(action="edit").exists()


@pytest.mark.django_db
def test_login_and_me_set_csrf_cookie(api, submitter):
    response = api.post("/api/auth/login/", {"username": "sam", "password": "password"}, format="json")
    assert response.status_code == 200
    assert "csrftoken" in response.cookies
    response = api.get("/api/me/")
    assert response.status_code == 200
    assert "csrftoken" in response.cookies


@pytest.mark.django_db
def test_csrf_is_enforced_on_unsafe_requests(submitter):
    api = APIClient(enforce_csrf_checks=True)
    response = api.post("/api/auth/login/", {"username": "sam", "password": "password"}, format="json")
    assert response.status_code == 200

    response = api.post(
        "/api/claims/",
        {"payer": "Acme", "service_date": "2026-09-01", "billed_amount": "100.00"},
        format="json",
    )
    assert response.status_code == 403

    token = api.cookies["csrftoken"].value
    response = api.post(
        "/api/claims/",
        {"payer": "Acme", "service_date": "2026-09-01", "billed_amount": "100.00"},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 201, response.content


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


@pytest.mark.django_db
def test_transition_endpoint_error_shapes(api, submitter, reviewer):
    claim = services.create_draft(created_by=submitter, billed_amount=Decimal("1.00"))
    login(api, "sam")
    url = f"/api/claims/{claim.id}/transition/"

    rule = api.post(url, {"action": "submit", "version": 0}, format="json")
    assert rule.status_code == 400 and set(rule.json()["errors"]) == {"payer", "service_date"}

    wrong_role = api.post(url, {"action": "approve", "version": 0, "data": {"approved_amount": "1"}}, format="json")
    assert wrong_role.status_code == 403

    unknown = api.post(url, {"action": "explode", "version": 0}, format="json")
    assert unknown.status_code == 400

    ok = api.post(url, {"action": "withdraw", "version": 0}, format="json")
    assert ok.status_code == 200 and ok.json()["state"] == "WITHDRAWN"

    review_claim = Claim.objects.create(
        payer="Acme", service_date=date(2026, 9, 1), billed_amount=Decimal("100.00"),
        submission_id="CH-X", state=State.UNDER_REVIEW, created_by=submitter,
    )
    review_url = f"/api/claims/{review_claim.id}/transition/"
    login(api, "rita")

    bad_decimal = api.post(review_url, {"action": "approve", "version": 0, "data": {"approved_amount": "lots"}}, format="json")
    assert bad_decimal.status_code == 400
    assert "approved_amount" in bad_decimal.json()["errors"]

    nan = api.post(review_url, {"action": "approve", "version": 0, "data": {"approved_amount": "nan"}}, format="json")
    assert nan.status_code == 400

    inf = api.post(review_url, {"action": "approve", "version": 0, "data": {"approved_amount": "inf"}}, format="json")
    assert inf.status_code == 400

    for amount in ("0.001", "50.005"):
        too_precise = api.post(
            review_url, {"action": "approve", "version": 0, "data": {"approved_amount": amount}}, format="json"
        )
        assert too_precise.status_code == 400, too_precise.content
        assert "approved_amount" in too_precise.json()["errors"]


@pytest.mark.django_db
def test_approved_amount_stored_matches_the_audit_record(api, submitter, reviewer):
    """What the claim stores and what the history says must be the same
    number: a scale the column would round is refused, not silently kept."""
    claim = Claim.objects.create(
        payer="Acme", service_date=date(2026, 9, 1), billed_amount=Decimal("100.00"),
        submission_id="CH-X", state=State.UNDER_REVIEW, created_by=submitter,
    )
    login(api, "rita")
    response = api.post(
        f"/api/claims/{claim.id}/transition/",
        {"action": "approve", "version": 0, "data": {"approved_amount": "50.50"}},
        format="json",
    )
    assert response.status_code == 200, response.content

    claim.refresh_from_db()
    assert claim.approved_amount == Decimal("50.50")
    event = claim.events.get(action="approve")
    assert event.data["approved_amount"] == "50.50"


@pytest.mark.django_db
def test_state_filter_applies_to_the_list_route_only(api, submitter):
    claim = services.create_draft(created_by=submitter, billed_amount=Decimal("1.00"))
    login(api, "sam")

    detail = api.get(f"/api/claims/{claim.id}/?state=DENIED")
    assert detail.status_code == 200 and detail.json()["state"] == "DRAFT"

    unknown = api.get("/api/claims/?state=bogus")
    assert unknown.status_code == 400
    assert "state" in unknown.json()


@pytest.mark.django_db
def test_other_submitters_claim_is_invisible_to_history_and_transition(api, submitter):
    other = User.objects.create_user("other", password="password", role=Role.SUBMITTER)
    claim = services.create_draft(created_by=other, billed_amount=Decimal("5.00"))
    login(api, "sam")

    assert api.get(f"/api/claims/{claim.id}/history/").status_code == 404
    response = api.post(
        f"/api/claims/{claim.id}/transition/", {"action": "withdraw", "version": 0}, format="json"
    )
    assert response.status_code == 404

    claim.refresh_from_db()
    assert (claim.state, claim.version) == (State.DRAFT, 0)
    assert [e.action for e in claim.events.all()] == ["create"]


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
        "submission_id": "", "next_attempt_at": None,
    }
    assert body["has_open_alert"] is True
    listed = api.get("/api/claims/?alert=open").json()
    assert [c["id"] for c in listed["results"]] == [claim.id]
    assert listed["results"][0]["has_open_alert"] is True
    assert api.get("/api/claims/?alert=bogus").status_code == 400

    pending_claim = Claim.objects.create(
        payer="Acme", service_date=date(2026, 9, 1), billed_amount=Decimal("1.00"),
        state=State.SUBMITTED, created_by=submitter,
    )
    Registration.objects.create(claim=pending_claim)
    pending_body = api.get(f"/api/claims/{pending_claim.id}/").json()
    assert pending_body["registration"]["status"] == "pending"
    assert isinstance(pending_body["registration"]["next_attempt_at"], str)


@pytest.mark.django_db
def test_retry_refused_without_a_registration_row(api, submitter, reviewer):
    draft = services.create_draft(created_by=submitter, billed_amount=Decimal("1.00"))
    login(api, "rita")
    response = api.post(f"/api/claims/{draft.id}/registration/retry/")
    assert response.status_code == 400
    assert response.json()["errors"] == {}


@pytest.mark.django_db
def test_retry_refused_when_halted(api, submitter, reviewer):
    claim, _ = failed_registration(submitter)
    Registration.objects.filter(claim=claim).update(status=RegistrationStatus.HALTED)
    login(api, "rita")
    response = api.post(f"/api/claims/{claim.id}/registration/retry/")
    assert response.status_code == 400
    assert "HALTED" in response.json()["detail"]


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
def test_retry_and_acknowledge_are_reviewer_only(api, submitter, reviewer):
    claim, alert = failed_registration(submitter)
    login(api, "sam")
    assert api.post(f"/api/claims/{claim.id}/registration/retry/").status_code == 403
    assert api.post(
        f"/api/claims/{claim.id}/acknowledge/", {"event_id": alert.id, "note": "x"}, format="json"
    ).status_code == 403


@pytest.mark.django_db
def test_retry_and_acknowledge_are_scoped(api, submitter, reviewer):
    other = User.objects.create_user("other", password="password", role=Role.SUBMITTER)
    claim, alert = failed_registration(other)
    login(api, "sam")
    assert api.post(f"/api/claims/{claim.id}/registration/retry/").status_code == 404
    assert api.post(
        f"/api/claims/{claim.id}/acknowledge/", {"event_id": alert.id, "note": "x"}, format="json"
    ).status_code == 404


@pytest.mark.django_db
def test_acknowledge_alert_requires_note_and_clears_flag(api, submitter, reviewer):
    claim, alert = failed_registration(submitter)
    login(api, "rita")
    url = f"/api/claims/{claim.id}/acknowledge/"
    missing = api.post(url, {"event_id": alert.id, "note": "  "}, format="json")
    assert missing.status_code == 400 and "note" in missing.json()["errors"]

    too_long = api.post(url, {"event_id": alert.id, "note": "x" * 2001}, format="json")
    assert too_long.status_code == 400 and "note" in too_long.json()["errors"]

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
def test_acknowledging_one_of_two_alerts_leaves_the_flag_open(api, submitter, reviewer):
    claim, first_alert = failed_registration(submitter)
    second_alert = ClaimEvent.objects.create(
        claim=claim, actor=None, action="duplicate_submission", severity=Severity.ALERT,
        from_state=claim.state, to_state=claim.state, data={},
    )
    login(api, "rita")
    url = f"/api/claims/{claim.id}/acknowledge/"

    first = api.post(url, {"event_id": first_alert.id, "note": "Looking into it."}, format="json")
    assert first.status_code == 200, first.content
    assert first.json()["has_open_alert"] is True

    second = api.post(url, {"event_id": second_alert.id, "note": "Confirmed a duplicate."}, format="json")
    assert second.status_code == 200, second.content
    assert second.json()["has_open_alert"] is False


@pytest.mark.django_db
def test_meta_lists_closed_lists(api, submitter):
    login(api, "sam")
    body = api.get("/api/meta/").json()
    assert [s["value"] for s in body["states"]] == list(State.values)
    assert all({"value", "label"} <= set(s) for s in body["states"])
    assert [d["value"] for d in body["denial_reasons"]] == [
        "not_covered", "duplicate", "insufficient_documentation", "out_of_network", "timely_filing",
    ]
    assert [r["value"] for r in body["registration_statuses"]] == ["pending", "in_flight", "done", "failed", "halted"]


@pytest.mark.django_db
def test_user_payload_carries_capabilities(api, submitter, reviewer):
    assert login(api, "sam")["can_create_claims"] is True
    api.post("/api/auth/logout/")
    assert login(api, "rita")["can_create_claims"] is False


@pytest.mark.django_db
def test_detail_can_edit_only_for_owner_draft(api, submitter, reviewer):
    claim = services.create_draft(created_by=submitter, payer="Acme", service_date=date(2026, 9, 1), billed_amount=Decimal("5.00"))
    login(api, "sam")
    assert api.get(f"/api/claims/{claim.id}/").json()["can_edit"] is True
    api.post(f"/api/claims/{claim.id}/transition/", {"action": "submit", "version": 0}, format="json")
    assert api.get(f"/api/claims/{claim.id}/").json()["can_edit"] is False
    api.post("/api/auth/logout/")
    login(api, "rita")
    assert api.get(f"/api/claims/{claim.id}/").json()["can_edit"] is False
