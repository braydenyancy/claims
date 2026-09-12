from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    SUBMITTER = "submitter", "Submitter"
    REVIEWER = "reviewer", "Reviewer"


class User(AbstractUser):
    """One role per user. Submitters create and submit claims; reviewers
    review them. The transition table keys on this field."""

    role = models.CharField(max_length=16, choices=Role.choices)
