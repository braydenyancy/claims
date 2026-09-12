import secrets

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import F, Q


class Role(models.TextChoices):
    SUBMITTER = "submitter", "Submitter"
    REVIEWER = "reviewer", "Reviewer"


class User(AbstractUser):
    """One role per user. Submitters create and submit claims; reviewers
    review them. The transition table keys on this field."""

    role = models.CharField(max_length=16, choices=Role.choices)


class State(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SUBMITTED = "SUBMITTED", "Submitted"
    UNDER_REVIEW = "UNDER_REVIEW", "Under review"
    INFO_REQUESTED = "INFO_REQUESTED", "Info requested"
    APPROVED = "APPROVED", "Approved"
    DENIED = "DENIED", "Denied"
    WITHDRAWN = "WITHDRAWN", "Withdrawn"


FINAL_STATES = frozenset({State.APPROVED, State.DENIED, State.WITHDRAWN})


class DenialReason(models.TextChoices):
    NOT_COVERED = "not_covered", "Service not covered"
    DUPLICATE = "duplicate", "Duplicate claim"
    INSUFFICIENT_DOCUMENTATION = "insufficient_documentation", "Insufficient documentation"
    OUT_OF_NETWORK = "out_of_network", "Out of network"
    TIMELY_FILING = "timely_filing", "Timely filing limit exceeded"


class Severity(models.TextChoices):
    INFO = "info", "Info"
    WARNING = "warning", "Warning"
    ALERT = "alert", "Alert"


def generate_reference() -> str:
    """Server-generated, unique, not guessable from a count. This is the
    idempotency key the clearinghouse recognises (D7)."""
    return f"CLM-{secrets.token_hex(4).upper()}"


class Claim(models.Model):
    reference = models.CharField(max_length=20, unique=True, editable=False)
    payer = models.CharField(max_length=200, blank=True)
    service_date = models.DateField(null=True, blank=True)
    billed_amount = models.DecimalField(max_digits=12, decimal_places=2)
    approved_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    denial_reason = models.CharField(max_length=32, choices=DenialReason.choices, blank=True)
    state = models.CharField(max_length=20, choices=State.choices, default=State.DRAFT)
    version = models.PositiveIntegerField(default=0)
    submission_id = models.CharField(max_length=40, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="claims"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(approved_amount__isnull=True)
                | (Q(approved_amount__gt=0) & Q(approved_amount__lte=F("billed_amount"))),
                name="claim_approved_within_billed",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = generate_reference()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.reference


class ImmutableEventError(Exception):
    """ClaimEvent rows are append-only."""


class ClaimEvent(models.Model):
    """One row per thing that happened to a claim: a user transition or a
    system outcome. Append-only at the model and at the database (D6)."""

    claim = models.ForeignKey(Claim, on_delete=models.PROTECT, related_name="events")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="claim_events",
    )
    action = models.CharField(max_length=40)
    from_state = models.CharField(max_length=20, choices=State.choices)
    to_state = models.CharField(max_length=20, choices=State.choices)
    data = models.JSONField(default=dict, blank=True)
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.INFO)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ImmutableEventError("ClaimEvent rows cannot be updated")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableEventError("ClaimEvent rows cannot be deleted")
