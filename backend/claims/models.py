import secrets

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


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
    lookup key used to reconcile an uncertain clearinghouse submission.
    The vendor does not enforce idempotency for this key.

    64 bits, not 32: by the birthday bound a 32-bit token collides with
    even odds after ~65k claims, which a single payer reaches. 16 hex
    characters plus the "CLM-" prefix is 20, the column's max_length."""
    return f"CLM-{secrets.token_hex(8).upper()}"


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
    has_open_alert = models.BooleanField(default=False)
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
    system outcome. Append-only at the model and at the database."""

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


class RegistrationStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    IN_FLIGHT = "IN_FLIGHT", "In flight"
    UNCERTAIN = "UNCERTAIN", "Needs reconciliation"
    DONE = "DONE", "Done"
    FAILED = "FAILED", "Failed"
    HALTED = "HALTED", "Halted"


class Registration(models.Model):
    """The outbox row for one claim's clearinghouse registration.
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
