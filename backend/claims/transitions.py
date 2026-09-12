"""The claim lifecycle as data (D4).

This module has no Django imports and is the single source of truth for
which action moves a claim from where to where, who may do it, what input
it needs, and what rule must hold. Enforcement (services.transition) and
the available-actions list (api) both read this table; neither keeps its
own copy of the rules.

States and roles are plain strings that mirror claims.models.State and
claims.models.Role, kept as strings so this module stays framework-free.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Callable, Protocol

DRAFT = "DRAFT"
SUBMITTED = "SUBMITTED"
UNDER_REVIEW = "UNDER_REVIEW"
INFO_REQUESTED = "INFO_REQUESTED"
APPROVED = "APPROVED"
DENIED = "DENIED"
WITHDRAWN = "WITHDRAWN"

SUBMITTER = "submitter"
REVIEWER = "reviewer"

DENIAL_REASONS = (
    "not_covered",
    "duplicate",
    "insufficient_documentation",
    "out_of_network",
    "timely_filing",
)


class ClaimView(Protocol):
    """The slice of a claim a rule may read."""

    payer: str
    service_date: date | None
    billed_amount: Decimal | None
    submission_id: str


Errors = dict[str, str]
Validator = Callable[[ClaimView, dict[str, Any], date], Errors]


@dataclass(frozen=True)
class Field:
    """An input a transition needs. The API renders it; the rule checks it."""

    name: str
    type: str  # "text" | "decimal" | "choice"
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class Transition:
    action: str
    label: str
    from_states: frozenset[str]
    to_state: str
    role: str
    fields: tuple[Field, ...] = ()
    writes: tuple[str, ...] = ()  # data keys copied onto the claim on success
    validate: Validator = lambda claim, data, today: {}


def _submit_rules(claim: ClaimView, data: dict, today: date) -> Errors:
    errors: Errors = {}
    if not claim.payer:
        errors["payer"] = "Payer is required."
    if claim.service_date is None:
        errors["service_date"] = "Service date is required."
    elif claim.service_date > today:
        errors["service_date"] = "Service date cannot be in the future."
    if claim.billed_amount is None or claim.billed_amount <= 0:
        errors["billed_amount"] = "Billed amount must be greater than zero."
    return errors


def _start_review_rules(claim: ClaimView, data: dict, today: date) -> Errors:
    if claim.submission_id:
        return {}
    return {"submission_id": "Claim has no clearinghouse submission ID yet."}


def _note_required(claim: ClaimView, data: dict, today: date) -> Errors:
    if str(data.get("note") or "").strip():
        return {}
    return {"note": "A note is required."}


def _approve_rules(claim: ClaimView, data: dict, today: date) -> Errors:
    amount = data.get("approved_amount")
    if amount is None:
        return {"approved_amount": "Approved amount is required."}
    if amount <= 0:
        return {"approved_amount": "Approved amount must be greater than zero."}
    if claim.billed_amount is not None and amount > claim.billed_amount:
        return {"approved_amount": "Approved amount cannot exceed the billed amount."}
    return {}


def _deny_rules(claim: ClaimView, data: dict, today: date) -> Errors:
    if data.get("denial_reason") in DENIAL_REASONS:
        return {}
    return {"denial_reason": "A denial reason from the fixed list is required."}


TRANSITIONS: dict[str, Transition] = {
    t.action: t
    for t in (
        Transition("submit", "Submit", frozenset({DRAFT}), SUBMITTED, SUBMITTER,
                   validate=_submit_rules),
        Transition("start_review", "Start review", frozenset({SUBMITTED}), UNDER_REVIEW, REVIEWER,
                   validate=_start_review_rules),
        Transition("request_info", "Request info", frozenset({UNDER_REVIEW}), INFO_REQUESTED, REVIEWER,
                   fields=(Field("note", "text"),), validate=_note_required),
        Transition("provide_info", "Provide info", frozenset({INFO_REQUESTED}), UNDER_REVIEW, SUBMITTER,
                   fields=(Field("note", "text"),), validate=_note_required),
        Transition("approve", "Approve", frozenset({UNDER_REVIEW}), APPROVED, REVIEWER,
                   fields=(Field("approved_amount", "decimal"),), writes=("approved_amount",),
                   validate=_approve_rules),
        Transition("deny", "Deny", frozenset({UNDER_REVIEW}), DENIED, REVIEWER,
                   fields=(Field("denial_reason", "choice", DENIAL_REASONS),), writes=("denial_reason",),
                   validate=_deny_rules),
        Transition("withdraw", "Withdraw", frozenset({DRAFT, INFO_REQUESTED}), WITHDRAWN, SUBMITTER),
    )
}


@dataclass(frozen=True)
class Available:
    """A transition this role may attempt from this state. If the rule can
    be evaluated without user input and fails, blocked_reason says why, so
    the UI can show the action disabled with the reason."""

    transition: Transition
    blocked_reason: str | None = None


def available_actions(claim: ClaimView, role: str, today: date, state: str | None = None) -> list[Available]:
    state = state if state is not None else getattr(claim, "state")
    result = []
    for t in TRANSITIONS.values():
        if state not in t.from_states or t.role != role:
            continue
        blocked = None
        if not t.fields:
            errors = t.validate(claim, {}, today)
            blocked = "; ".join(errors.values()) or None
        result.append(Available(t, blocked))
    return result
