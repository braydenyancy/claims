"""Requirement 1: claims change state only through the seven transitions,
with rules and roles enforced. The matrix test walks every action from
every state for both roles and checks the outcome against the table, so
the table is proved rather than sampled."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from claims import services, transitions
from claims.models import Claim, ClaimEvent, DenialReason, Role, State, User

ALL_STATES = [s.value for s in State]
ALL_ACTIONS = list(transitions.TRANSITIONS)

# The literal shape of the table, independent of transitions.TRANSITIONS itself,
# so a change to the table's from-states, target, or role is caught even though
# the matrix test above derives its own expectation from the same table.
EXPECTED_TABLE = [
    ("submit", frozenset({State.DRAFT}), State.SUBMITTED, Role.SUBMITTER),
    ("start_review", frozenset({State.SUBMITTED}), State.UNDER_REVIEW, Role.REVIEWER),
    ("request_info", frozenset({State.UNDER_REVIEW}), State.INFO_REQUESTED, Role.REVIEWER),
    ("provide_info", frozenset({State.INFO_REQUESTED}), State.UNDER_REVIEW, Role.SUBMITTER),
    ("approve", frozenset({State.UNDER_REVIEW}), State.APPROVED, Role.REVIEWER),
    ("deny", frozenset({State.UNDER_REVIEW}), State.DENIED, Role.REVIEWER),
    ("withdraw", frozenset({State.DRAFT, State.INFO_REQUESTED}), State.WITHDRAWN, Role.SUBMITTER),
]

# Input that satisfies each transition's rule when the claim itself is complete.
VALID_DATA = {
    "request_info": {"note": "Please attach the operative report."},
    "provide_info": {"note": "Attached."},
    "approve": {"approved_amount": Decimal("80.00")},
    "deny": {"denial_reason": "duplicate"},
}


def make_claim(submitter, state, **overrides):
    fields = dict(
        payer="Acme Health",
        service_date=date(2026, 9, 1),
        billed_amount=Decimal("100.00"),
        submission_id="CH-TEST000001",
        state=state,
        created_by=submitter,
    )
    fields.update(overrides)
    return Claim.objects.create(**fields)


def test_closed_lists_match_models():
    """transitions.py has no Django import, so its closed lists (denial
    reasons, states, roles) are copies of the ones models.py defines. Pin
    them together so the two cannot drift apart silently."""
    assert set(transitions.DENIAL_REASONS) == {c for c, _ in DenialReason.choices}
    assert {
        transitions.DRAFT, transitions.SUBMITTED, transitions.UNDER_REVIEW,
        transitions.INFO_REQUESTED, transitions.APPROVED, transitions.DENIED,
        transitions.WITHDRAWN,
    } == {c for c, _ in State.choices}
    assert {transitions.SUBMITTER, transitions.REVIEWER} == {c for c, _ in Role.choices}


def test_transition_table_matches_literal_spec():
    """The matrix test below derives its expectation from TRANSITIONS itself,
    so it cannot catch a wrong from_states/to_state/role written into the
    table. Pin the table against a literal, independently-written spec."""
    actual = [(t.action, t.from_states, t.to_state, t.role) for t in transitions.TRANSITIONS.values()]
    assert actual == EXPECTED_TABLE


@pytest.mark.django_db
@pytest.mark.parametrize("action", ALL_ACTIONS)
@pytest.mark.parametrize("state", ALL_STATES)
@pytest.mark.parametrize("role", [Role.SUBMITTER, Role.REVIEWER])
def test_matrix(submitter, reviewer, action, state, role):
    actor = submitter if role == Role.SUBMITTER else reviewer
    claim = make_claim(submitter, state)
    t = transitions.TRANSITIONS[action]
    allowed = state in t.from_states and t.role == role

    if allowed:
        result = services.transition(
            claim_id=claim.pk, action=action, actor=actor,
            expected_version=0, data=VALID_DATA.get(action),
        )
        assert result.state == t.to_state
        assert result.version == 1
        event = ClaimEvent.objects.get(claim=claim, action=action)
        assert (event.from_state, event.to_state, event.actor) == (state, t.to_state, actor)
    else:
        with pytest.raises(services.NotAllowed):
            services.transition(
                claim_id=claim.pk, action=action, actor=actor,
                expected_version=0, data=VALID_DATA.get(action),
            )
        claim.refresh_from_db()
        assert claim.state == state
        assert claim.version == 0
        assert not ClaimEvent.objects.filter(claim=claim).exists()


@pytest.mark.django_db
def test_final_states_offer_no_actions(submitter):
    for state in (State.APPROVED, State.DENIED, State.WITHDRAWN):
        claim = make_claim(submitter, state)
        for role in (Role.SUBMITTER, Role.REVIEWER):
            assert transitions.available_actions(claim, role, date(2026, 9, 12)) == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"payer": ""}, "payer"),
        ({"service_date": None}, "service_date"),
        ({"service_date": date.today() + timedelta(days=2)}, "service_date"),
        ({"billed_amount": Decimal("0.00")}, "billed_amount"),
    ],
)
def test_submit_rules(submitter, overrides, field):
    claim = make_claim(submitter, State.DRAFT, submission_id="", **overrides)
    with pytest.raises(services.RuleViolation) as exc:
        services.transition(claim_id=claim.pk, action="submit", actor=submitter, expected_version=0)
    assert field in exc.value.errors


@pytest.mark.django_db
def test_start_review_requires_submission_id(submitter, reviewer):
    claim = make_claim(submitter, State.SUBMITTED, submission_id="")
    with pytest.raises(services.RuleViolation) as exc:
        services.transition(claim_id=claim.pk, action="start_review", actor=reviewer, expected_version=0)
    assert "submission_id" in exc.value.errors
    blocked = transitions.available_actions(claim, Role.REVIEWER, date(2026, 9, 12))
    assert [a.transition.action for a in blocked] == ["start_review"]
    assert blocked[0].blocked_reason


@pytest.mark.django_db
@pytest.mark.parametrize("action, state, actor_role", [
    ("request_info", State.UNDER_REVIEW, Role.REVIEWER),
    ("provide_info", State.INFO_REQUESTED, Role.SUBMITTER),
])
@pytest.mark.parametrize("note", ["", "   ", None])
def test_notes_are_required(submitter, reviewer, action, state, actor_role, note):
    claim = make_claim(submitter, state)
    actor = submitter if actor_role == Role.SUBMITTER else reviewer
    with pytest.raises(services.RuleViolation) as exc:
        services.transition(
            claim_id=claim.pk, action=action, actor=actor, expected_version=0,
            data={} if note is None else {"note": note},
        )
    assert "note" in exc.value.errors


@pytest.mark.django_db
@pytest.mark.parametrize("amount", [
    None, Decimal("0.00"), Decimal("-1.00"), Decimal("100.01"), "80.00",
    Decimal("0.001"), Decimal("50.005"),
])
def test_approve_amount_rules(submitter, reviewer, amount):
    claim = make_claim(submitter, State.UNDER_REVIEW)
    data = {} if amount is None else {"approved_amount": amount}
    with pytest.raises(services.RuleViolation) as exc:
        services.transition(claim_id=claim.pk, action="approve", actor=reviewer, expected_version=0, data=data)
    assert "approved_amount" in exc.value.errors


@pytest.mark.django_db
def test_approve_stores_amount(submitter, reviewer):
    claim = make_claim(submitter, State.UNDER_REVIEW)
    result = services.transition(
        claim_id=claim.pk, action="approve", actor=reviewer, expected_version=0,
        data={"approved_amount": Decimal("100.00")},
    )
    assert result.approved_amount == Decimal("100.00")
    assert ClaimEvent.objects.get(claim=claim, action="approve").data == {"approved_amount": "100.00"}


@pytest.mark.django_db
def test_extra_data_keys_are_not_stored(submitter, reviewer):
    claim = make_claim(submitter, State.UNDER_REVIEW)
    services.transition(
        claim_id=claim.pk, action="approve", actor=reviewer, expected_version=0,
        data={"approved_amount": Decimal("50.00"), "extra": "not declared"},
    )
    event = ClaimEvent.objects.get(claim=claim, action="approve")
    assert event.data == {"approved_amount": "50.00"}


@pytest.mark.django_db
@pytest.mark.parametrize("reason", [None, "", "because"])
def test_deny_requires_listed_reason(submitter, reviewer, reason):
    claim = make_claim(submitter, State.UNDER_REVIEW)
    data = {} if reason is None else {"denial_reason": reason}
    with pytest.raises(services.RuleViolation) as exc:
        services.transition(claim_id=claim.pk, action="deny", actor=reviewer, expected_version=0, data=data)
    assert "denial_reason" in exc.value.errors


@pytest.mark.django_db
def test_deny_stores_reason(submitter, reviewer):
    claim = make_claim(submitter, State.UNDER_REVIEW)
    result = services.transition(
        claim_id=claim.pk, action="deny", actor=reviewer, expected_version=0,
        data={"denial_reason": "out_of_network"},
    )
    assert result.denial_reason == "out_of_network"


@pytest.mark.django_db
def test_stale_version_conflicts(submitter):
    claim = make_claim(submitter, State.DRAFT, submission_id="")
    services.transition(claim_id=claim.pk, action="submit", actor=submitter, expected_version=0)
    with pytest.raises(services.ConflictError) as exc:
        services.transition(claim_id=claim.pk, action="withdraw", actor=submitter, expected_version=0)
    assert exc.value.claim.version == 1
    assert exc.value.claim.state == State.SUBMITTED


@pytest.mark.django_db
def test_submitter_cannot_act_on_another_submitters_claim(submitter, db):
    other = User.objects.create_user("other", password="password", role=Role.SUBMITTER)
    claim = make_claim(submitter, State.DRAFT, submission_id="")
    with pytest.raises(services.NotAllowed):
        services.transition(claim_id=claim.pk, action="submit", actor=other, expected_version=0)
    # Ownership is checked before the version check: a stale version on a claim
    # the actor doesn't own is still NotAllowed, not ConflictError.
    with pytest.raises(services.NotAllowed):
        services.transition(claim_id=claim.pk, action="submit", actor=other, expected_version=99)


@pytest.mark.django_db
def test_create_draft_writes_create_event(submitter):
    claim = services.create_draft(
        created_by=submitter, payer="Acme", service_date=date(2026, 9, 1), billed_amount=Decimal("10.00")
    )
    assert claim.state == State.DRAFT
    event = ClaimEvent.objects.get(claim=claim)
    assert (event.action, event.actor, event.from_state, event.to_state) == ("create", submitter, State.DRAFT, State.DRAFT)


@pytest.mark.django_db
def test_update_draft_records_changed_fields(submitter):
    claim = services.create_draft(created_by=submitter, billed_amount=Decimal("10.00"))
    services.update_draft(claim=claim, actor=submitter, payer="Acme", billed_amount=Decimal("20.00"))
    claim.refresh_from_db()
    assert (claim.payer, claim.billed_amount) == ("Acme", Decimal("20.00"))
    assert claim.version == 1
    event = ClaimEvent.objects.get(claim=claim, action="edit")
    assert event.data == {"payer": "Acme", "billed_amount": "20.00"}
    # The edit bumped the version, so a transition still holding version 0 is stale.
    with pytest.raises(services.ConflictError):
        services.transition(claim_id=claim.pk, action="withdraw", actor=submitter, expected_version=0)


@pytest.mark.django_db
def test_update_draft_refused_outside_draft(submitter):
    claim = make_claim(submitter, State.SUBMITTED)
    with pytest.raises(services.NotAllowed):
        services.update_draft(claim=claim, actor=submitter, payer="X")


@pytest.mark.django_db
def test_update_draft_refused_for_non_owner(submitter, reviewer):
    claim = services.create_draft(created_by=submitter, billed_amount=Decimal("10.00"))
    with pytest.raises(services.NotAllowed):
        services.update_draft(claim=claim, actor=reviewer, payer="X")
