# Stage 1: Backend Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The full claim lifecycle works over a DRF API under docker compose, with rules, roles, conflicts and an immutable history enforced and tested.

**Architecture:** One Django app (`claims`). The lifecycle is a declarative table in `transitions.py` with no Django imports; `services.py` enforces it inside a transaction with a row lock and a version check and writes the audit event in the same transaction; `api/` is a thin DRF layer that maps service exceptions to HTTP codes and renders the available-actions list from the same table. Postgres holds a trigger that makes the event table append-only.

**Tech Stack:** Python 3.13, Django 5.2, Django REST Framework 3.16, psycopg 3, PostgreSQL 17, uv, pytest + pytest-django, docker compose.

**Spec:** `docs/specs/2026-09-12-stage-1-backend-core.md` (binding). Decisions: `docs/architecture/DECISIONS.md`. Workflows: `docs/architecture/WORKFLOWS.md`.

## Global Constraints

- Dependencies are exactly: `django>=5.2,<5.3`, `djangorestframework>=3.16,<3.17`, `psycopg[binary]>=3.2,<4`; dev: `pytest>=8`, `pytest-django>=4.11`. Nothing else without a ruling.
- `backend/claims/transitions.py` has no Django imports. It is the only place lifecycle rules live.
- Money is `Decimal`, never float. `TIME_ZONE = "UTC"`, `USE_TZ = True`.
- Every state change and its `ClaimEvent` commit in one transaction.
- `vendor/clearinghouse.py` is never modified or imported in stage 1.
- Commit messages: subject + body only. No tool, model, or assistant attribution of any kind, no `Co-Authored-By` naming a tool.
- Tests run locally with `cd backend && uv run pytest` against the compose Postgres on host port 5433 (`docker compose up -d postgres` from the repo root). Every task ends with the full suite green.
- Denial reasons (fixed list): `not_covered`, `duplicate`, `insufficient_documentation`, `out_of_network`, `timely_filing`.
- Seeded logins: `sam` (submitter), `rita` and `rob` (reviewers), all with password `password`.
- Postgres credentials in dev: db `claims`, user `claims`, password `claims`.

---

### Task 1: Skeleton that boots under compose

**Files:**
- Create: `compose.yaml`, `.env.example`, `README.md`
- Create: `backend/pyproject.toml`, `backend/Dockerfile`, `backend/entrypoint.sh`, `backend/manage.py`
- Create: `backend/config/__init__.py`, `backend/config/settings.py`, `backend/config/urls.py`, `backend/config/wsgi.py`
- Create: `backend/claims/__init__.py`, `backend/claims/apps.py`, `backend/claims/models.py`, `backend/claims/migrations/__init__.py`, `backend/claims/migrations/0001_initial.py` (generated)
- Create: `backend/claims/api/__init__.py`, `backend/claims/api/views.py`, `backend/claims/api/urls.py`
- Create: `backend/claims/tests/__init__.py`, `backend/claims/tests/conftest.py`, `backend/claims/tests/test_health.py`

**Interfaces:**
- Produces: `claims.User` (custom user, `role` field) as `AUTH_USER_MODEL`; `GET /api/health/` → `{"status": "ok", "database": "ok"}`; settings reading `POSTGRES_*` from the environment.

- [ ] **Step 1: Create the Python project**

`backend/pyproject.toml`:

```toml
[project]
name = "claims-backend"
version = "0.1.0"
description = "Claim review workflow API"
requires-python = ">=3.13"
dependencies = [
    "django>=5.2,<5.3",
    "djangorestframework>=3.16,<3.17",
    "psycopg[binary]>=3.2,<4",
]

[dependency-groups]
dev = [
    "pytest>=8",
    "pytest-django>=4.11",
]

[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "config.settings"
python_files = ["test_*.py"]
testpaths = ["claims/tests"]
```

Run from `backend/`: `uv lock` then `uv sync`. Commit `uv.lock`.

- [ ] **Step 2: Django project files**

`backend/manage.py`:

```python
#!/usr/bin/env python
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
```

`backend/config/__init__.py`: empty.

`backend/config/settings.py`:

```python
"""Django settings. Every environment-specific value comes from the
environment with a development default; nothing secret lives here."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "rest_framework",
    "claims",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "claims"),
        "USER": os.environ.get("POSTGRES_USER", "claims"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "claims"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5433"),
    }
}

AUTH_USER_MODEL = "claims.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}

# Session cookie is the credential; CSRF cookie is readable so the SPA
# can echo it in the X-CSRFToken header.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = os.environ.get(
    "CSRF_TRUSTED_ORIGINS", "http://localhost:5173,http://localhost:8000"
).split(",")

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
```

`backend/config/urls.py`:

```python
from django.urls import include, path

urlpatterns = [
    path("api/", include("claims.api.urls")),
]
```

`backend/config/wsgi.py`:

```python
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()
```

- [ ] **Step 3: The claims app with the custom user**

`backend/claims/__init__.py`: empty. `backend/claims/migrations/__init__.py`: empty. `backend/claims/api/__init__.py`: empty. `backend/claims/tests/__init__.py`: empty.

`backend/claims/apps.py`:

```python
from django.apps import AppConfig


class ClaimsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "claims"
```

`backend/claims/models.py`:

```python
from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    SUBMITTER = "submitter", "Submitter"
    REVIEWER = "reviewer", "Reviewer"


class User(AbstractUser):
    """One role per user. Submitters create and submit claims; reviewers
    review them. The transition table keys on this field."""

    role = models.CharField(max_length=16, choices=Role.choices)
```

`backend/claims/api/views.py`:

```python
from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Liveness plus a database round trip. Unauthenticated on purpose:
    compose and humans use it to know the stack is up."""

    permission_classes = [AllowAny]

    def get(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return Response({"status": "ok", "database": "ok"})
```

`backend/claims/api/urls.py`:

```python
from django.urls import path

from .views import HealthView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
]
```

- [ ] **Step 4: Compose, Dockerfile, entrypoint**

`compose.yaml` at the repo root:

```yaml
services:
  postgres:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: claims
      POSTGRES_USER: claims
      POSTGRES_PASSWORD: claims
    ports:
      - "5433:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U claims -d claims"]
      interval: 2s
      timeout: 2s
      retries: 30

  api:
    build:
      context: .
      dockerfile: backend/Dockerfile
    command: python manage.py runserver 0.0.0.0:8000
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_PORT: "5432"
      POSTGRES_DB: claims
      POSTGRES_USER: claims
      POSTGRES_PASSWORD: claims
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app
      - ./vendor:/app/vendor
    depends_on:
      postgres:
        condition: service_healthy

volumes:
  pgdata:
```

`backend/Dockerfile`:

```dockerfile
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/usr/local \
    PYTHONPATH=/app/vendor

COPY --from=ghcr.io/astral-sh/uv:0.12.12 /uv /usr/local/bin/uv

WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen

COPY backend/ /app/
COPY vendor/ /app/vendor/
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
```

`backend/entrypoint.sh`:

```sh
#!/bin/sh
set -e
python manage.py migrate --noinput
exec "$@"
```

`.env.example`:

```
# Development defaults. compose.yaml sets these for containers; copy to
# .env only if you run the backend outside compose.
POSTGRES_DB=claims
POSTGRES_USER=claims
POSTGRES_PASSWORD=claims
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
DJANGO_SECRET_KEY=dev-only-insecure-key-change-me
DJANGO_DEBUG=1
```

`README.md`:

```markdown
# Claims

Claim review workflow: Django + DRF + PostgreSQL API, Vue 3 frontend.

## Run

    docker compose up

API on http://localhost:8000/api/. Health: `GET /api/health/`.

## Develop

    docker compose up -d postgres
    cd backend && uv sync && uv run pytest

## Layout

- `backend/` Django project and the `claims` app
- `vendor/` third-party code used as-is (the clearinghouse client)
- `docs/` compliance program, decisions, workflows, specs, plans
```

- [ ] **Step 5: Generate the initial migration**

From the repo root: `docker compose up -d postgres`. From `backend/`: `uv run python manage.py makemigrations claims` and confirm it creates `claims/migrations/0001_initial.py` with the `User` model. Then `uv run python manage.py migrate`.

- [ ] **Step 6: Write the failing test**

`backend/claims/tests/conftest.py`:

```python
import pytest

from claims.models import Role, User


@pytest.fixture
def submitter(db):
    return User.objects.create_user("sam", password="password", role=Role.SUBMITTER)


@pytest.fixture
def reviewer(db):
    return User.objects.create_user("rita", password="password", role=Role.REVIEWER)


@pytest.fixture
def reviewer2(db):
    return User.objects.create_user("rob", password="password", role=Role.REVIEWER)
```

`backend/claims/tests/test_health.py`:

```python
import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_health_reports_ok():
    response = APIClient().get("/api/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


@pytest.mark.django_db
def test_user_has_role(submitter):
    assert submitter.role == "submitter"
```

- [ ] **Step 7: Run tests**

Run from `backend/`: `uv run pytest -v`. Expected: 2 passed.

- [ ] **Step 8: Verify compose boots**

From the repo root: `docker compose up --build -d` then `curl -s localhost:8000/api/health/`. Expected: `{"status":"ok","database":"ok"}`. Then `docker compose down`.

- [ ] **Step 9: Commit**

```bash
git add compose.yaml .env.example README.md backend
git commit -m "Add backend skeleton that boots under compose

Django 5.2 project with DRF, a custom user carrying a role, Postgres
settings read from the environment, and a health endpoint. Compose
runs Postgres and the API; the API image migrates on start."
```

---

### Task 2: Claim and ClaimEvent models with database-level guarantees

**Files:**
- Modify: `backend/claims/models.py`
- Create: `backend/claims/migrations/0002_claim_claimevent.py` (generated), `backend/claims/migrations/0003_claimevent_immutable.py` (hand-written)
- Modify: `backend/claims/tests/conftest.py`
- Create: `backend/claims/tests/test_audit.py`

**Interfaces:**
- Consumes: `claims.User`, `Role` from Task 1.
- Produces: `State`, `FINAL_STATES`, `DenialReason`, `Severity`, `Claim`, `ClaimEvent`, `ImmutableEventError`, `generate_reference()`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/claims/tests/conftest.py`:

```python
from decimal import Decimal
from datetime import date

from claims.models import Claim


@pytest.fixture
def claim(submitter):
    return Claim.objects.create(
        payer="Acme Health",
        service_date=date(2026, 9, 1),
        billed_amount=Decimal("100.00"),
        created_by=submitter,
    )
```

`backend/claims/tests/test_audit.py`:

```python
"""Requirement 3: history cannot be edited or deleted. Three layers are
tested: the model refuses, the ORM bulk path is stopped by the trigger,
and the trigger stops raw SQL too."""

import pytest
from django.db import DatabaseError, connection, transaction

from claims.models import ClaimEvent, ImmutableEventError, State


def _event(claim):
    return ClaimEvent.objects.create(
        claim=claim, action="submit", from_state=State.DRAFT, to_state=State.SUBMITTED
    )


@pytest.mark.django_db
def test_model_refuses_update(claim):
    event = _event(claim)
    event.action = "tampered"
    with pytest.raises(ImmutableEventError):
        event.save()


@pytest.mark.django_db
def test_model_refuses_delete(claim):
    event = _event(claim)
    with pytest.raises(ImmutableEventError):
        event.delete()


@pytest.mark.django_db
def test_database_rejects_queryset_update(claim):
    event = _event(claim)
    with pytest.raises(DatabaseError), transaction.atomic():
        ClaimEvent.objects.filter(pk=event.pk).update(action="tampered")


@pytest.mark.django_db
def test_database_rejects_raw_delete(claim):
    event = _event(claim)
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("DELETE FROM claims_claimevent WHERE id = %s", [event.pk])


@pytest.mark.django_db
def test_claim_gets_server_generated_reference(claim):
    assert claim.reference.startswith("CLM-")
    assert len(claim.reference) == 12


@pytest.mark.django_db
def test_approved_amount_cannot_exceed_billed(claim):
    claim.approved_amount = claim.billed_amount + 1
    with pytest.raises(DatabaseError), transaction.atomic():
        claim.save()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest claims/tests/test_audit.py -v`. Expected: ImportError on `Claim`.

- [ ] **Step 3: Add the models**

Replace `backend/claims/models.py` with:

```python
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
```

- [ ] **Step 4: Generate the model migration, then hand-write the trigger migration**

From `backend/`: `uv run python manage.py makemigrations claims -n claim_claimevent`. Confirm it produced `0002_claim_claimevent.py`.

Create `backend/claims/migrations/0003_claimevent_immutable.py`:

```python
"""Append-only audit table, enforced below the application (D6).
A trigger rather than REVOKE so it holds with a single database role."""

from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION claims_claimevent_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'claims_claimevent is append-only (% refused)', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER claims_claimevent_immutable
    BEFORE UPDATE OR DELETE ON claims_claimevent
    FOR EACH ROW EXECUTE FUNCTION claims_claimevent_immutable();
"""

BACKWARD = """
DROP TRIGGER IF EXISTS claims_claimevent_immutable ON claims_claimevent;
DROP FUNCTION IF EXISTS claims_claimevent_immutable();
"""


class Migration(migrations.Migration):
    dependencies = [("claims", "0002_claim_claimevent")]
    operations = [migrations.RunSQL(FORWARD, BACKWARD)]
```

Run `uv run python manage.py migrate`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest -v`. Expected: all pass (8 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/claims
git commit -m "Add Claim and ClaimEvent with append-only enforcement

Claim carries a server-generated reference, a version for optimistic
locking, and a check constraint keeping the approved amount within the
billed amount. ClaimEvent is one table for user transitions and system
outcomes; the model refuses updates and deletes, and a Postgres trigger
refuses them for any path that bypasses the model."
```

---

### Task 3: Transition table and service

**Files:**
- Create: `backend/claims/transitions.py`, `backend/claims/services.py`
- Create: `backend/claims/tests/test_transitions.py`

**Interfaces:**
- Consumes: models from Task 2.
- Produces:
  - `transitions.TRANSITIONS: dict[str, Transition]`, `transitions.Transition(action, label, from_states, to_state, role, fields, writes, validate)`, `transitions.Field(name, type, choices)`, `transitions.available_actions(claim, role, today) -> list[Available]` where `Available(transition, blocked_reason: str | None)`.
  - `services.create_draft(*, created_by, payer="", service_date=None, billed_amount) -> Claim`
  - `services.update_draft(*, claim, actor, **fields) -> Claim`
  - `services.transition(*, claim_id, action, actor, expected_version, data=None) -> Claim`
  - Exceptions: `services.TransitionError` (base), `services.ConflictError(claim)`, `services.NotAllowed(message, status_code)`, `services.RuleViolation(errors: dict[str, str])`.

- [ ] **Step 1: Write the failing tests**

`backend/claims/tests/test_transitions.py`:

```python
"""Requirement 1: claims change state only through the seven transitions,
with rules and roles enforced. The matrix test walks every action from
every state for both roles and checks the outcome against the table, so
the table is proved rather than sampled."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from claims import services, transitions
from claims.models import Claim, ClaimEvent, Role, State

ALL_STATES = [s.value for s in State]
ALL_ACTIONS = list(transitions.TRANSITIONS)

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
@pytest.mark.parametrize("amount", [None, Decimal("0.00"), Decimal("-1.00"), Decimal("100.01")])
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
    from claims.models import User
    other = User.objects.create_user("other", password="password", role=Role.SUBMITTER)
    claim = make_claim(submitter, State.DRAFT, submission_id="")
    with pytest.raises(services.NotAllowed):
        services.transition(claim_id=claim.pk, action="submit", actor=other, expected_version=0)


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
    event = ClaimEvent.objects.get(claim=claim, action="edit")
    assert event.data == {"payer": "Acme", "billed_amount": "20.00"}


@pytest.mark.django_db
def test_update_draft_refused_outside_draft(submitter):
    claim = make_claim(submitter, State.SUBMITTED)
    with pytest.raises(services.NotAllowed):
        services.update_draft(claim=claim, actor=submitter, payer="X")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest claims/tests/test_transitions.py -q`. Expected: ImportError on `claims.services`.

- [ ] **Step 3: Write the transition table**

`backend/claims/transitions.py`:

```python
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
```

- [ ] **Step 4: Write the service**

`backend/claims/services.py`:

```python
"""The only writers of claim state. Every state change happens here,
inside one transaction, behind a row lock and a version check, and
writes its ClaimEvent before committing (D5, D6)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from . import transitions
from .models import Claim, ClaimEvent, Role, State, User


class TransitionError(Exception):
    """Base for refused transitions."""


class ConflictError(TransitionError):
    """The claim changed since the caller last saw it (D5)."""

    def __init__(self, claim: Claim):
        self.claim = claim
        super().__init__("Claim was modified by someone else.")


class NotAllowed(TransitionError):
    """Wrong role, wrong owner, wrong state, or unknown action."""

    def __init__(self, message: str, status_code: int = 403):
        self.status_code = status_code
        super().__init__(message)


class RuleViolation(TransitionError):
    """The transition's rule did not hold. errors maps field to message."""

    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__("Transition rules not satisfied.")


def _jsonable(data: dict[str, Any]) -> dict[str, Any]:
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in data.items()}


def _check_owner(claim: Claim, actor: User) -> None:
    if actor.role == Role.SUBMITTER and claim.created_by_id != actor.id:
        raise NotAllowed("You can only act on your own claims.", 403)


def create_draft(*, created_by: User, payer: str = "", service_date=None, billed_amount: Decimal) -> Claim:
    if created_by.role != Role.SUBMITTER:
        raise NotAllowed("Only submitters create claims.", 403)
    with transaction.atomic():
        claim = Claim.objects.create(
            payer=payer, service_date=service_date, billed_amount=billed_amount, created_by=created_by
        )
        ClaimEvent.objects.create(
            claim=claim, actor=created_by, action="create",
            from_state=State.DRAFT, to_state=State.DRAFT, data={},
        )
    return claim


def update_draft(*, claim: Claim, actor: User, **fields: Any) -> Claim:
    """Edit a draft's payer, service_date or billed_amount. Recorded as an
    `edit` event carrying the changed fields, so the history is complete."""
    allowed = {"payer", "service_date", "billed_amount"}
    unknown = set(fields) - allowed
    if unknown:
        raise NotAllowed(f"Cannot edit {', '.join(sorted(unknown))}.", 400)
    with transaction.atomic():
        claim = Claim.objects.select_for_update().get(pk=claim.pk)
        _check_owner(claim, actor)
        if claim.state != State.DRAFT:
            raise NotAllowed("Only drafts can be edited.", 400)
        changed = {k: v for k, v in fields.items() if getattr(claim, k) != v}
        if not changed:
            return claim
        for k, v in changed.items():
            setattr(claim, k, v)
        claim.save()
        ClaimEvent.objects.create(
            claim=claim, actor=actor, action="edit",
            from_state=State.DRAFT, to_state=State.DRAFT,
            data=_jsonable({k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in changed.items()}),
        )
    return claim


def transition(*, claim_id: int, action: str, actor: User, expected_version: int, data: dict[str, Any] | None = None) -> Claim:
    data = dict(data or {})
    t = transitions.TRANSITIONS.get(action)
    if t is None:
        raise NotAllowed(f"Unknown action '{action}'.", 400)

    with transaction.atomic():
        claim = Claim.objects.select_for_update().get(pk=claim_id)
        if claim.version != expected_version:
            raise ConflictError(claim)
        _check_owner(claim, actor)
        if actor.role != t.role:
            raise NotAllowed(f"Only a {t.role} can {action}.", 403)
        if claim.state not in t.from_states:
            raise NotAllowed(f"Cannot {action} a claim in state {claim.state}.", 400)

        errors = t.validate(claim, data, timezone.localdate())
        if errors:
            raise RuleViolation(errors)

        from_state = claim.state
        for name in t.writes:
            setattr(claim, name, data[name])
        claim.state = t.to_state
        claim.version += 1
        claim.save()
        ClaimEvent.objects.create(
            claim=claim, actor=actor, action=action,
            from_state=from_state, to_state=t.to_state, data=_jsonable(data),
        )
    return claim
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest -q`. Expected: all pass. The matrix alone is 98 cases.

- [ ] **Step 6: Commit**

```bash
git add backend/claims/transitions.py backend/claims/services.py backend/claims/tests/test_transitions.py
git commit -m "Add the transition table and the claim service

transitions.py holds the seven transitions as data with no Django
imports: from-states, target, role, input fields, and a rule function.
services.transition enforces it under a row lock and a version check
and writes the audit event in the same transaction. The matrix test
walks every action from every state for both roles."
```

---

### Task 4: Idempotent seed

**Files:**
- Create: `backend/claims/management/__init__.py`, `backend/claims/management/commands/__init__.py`, `backend/claims/management/commands/seed.py`
- Modify: `backend/entrypoint.sh`
- Create: `backend/claims/tests/test_seed.py`

**Interfaces:**
- Consumes: `services.create_draft`, `services.transition`, models.
- Produces: `python manage.py seed`; users `sam`, `rita`, `rob`.

- [ ] **Step 1: Write the failing test**

`backend/claims/tests/test_seed.py`:

```python
import pytest
from django.core.management import call_command

from claims.models import Claim, ClaimEvent, State, User


@pytest.mark.django_db
def test_seed_creates_users_and_claims_once():
    call_command("seed")
    call_command("seed")
    assert sorted(User.objects.values_list("username", flat=True)) == ["rita", "rob", "sam"]
    assert set(Claim.objects.values_list("state", flat=True)) == set(State.values)
    assert Claim.objects.count() == 9
    assert ClaimEvent.objects.filter(action="create").count() == 9
    assert User.objects.get(username="sam").check_password("password")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest claims/tests/test_seed.py -q`. Expected: CommandError, unknown command "seed".

- [ ] **Step 3: Write the command**

`backend/claims/management/__init__.py` and `backend/claims/management/commands/__init__.py`: empty.

`backend/claims/management/commands/seed.py`:

```python
"""Seed users and sample claims. Idempotent: users are get-or-created,
claims are created only when none exist. Claims are built through the
service layer so their histories are real."""

from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from claims import services
from claims.models import Claim, Role, User

USERS = [
    ("sam", Role.SUBMITTER),
    ("rita", Role.REVIEWER),
    ("rob", Role.REVIEWER),
]

# Stage 1 has no clearinghouse worker, so a submission ID is stamped on
# directly where the sample needs one. Stage 2 replaces this.
SEED_SUBMISSION_ID = "CH-SEED000001"


class Command(BaseCommand):
    help = "Seed sample users and claims"

    def handle(self, *args, **options):
        users = {}
        for username, role in USERS:
            user, created = User.objects.get_or_create(username=username, defaults={"role": role})
            if created:
                user.set_password("password")
                user.save()
            users[username] = user
        self.stdout.write(f"users: {', '.join(users)}")

        if Claim.objects.exists():
            self.stdout.write("claims: already seeded")
            return

        sam, rita, rob = users["sam"], users["rita"], users["rob"]

        def draft(payer, day, amount):
            return services.create_draft(
                created_by=sam, payer=payer, service_date=date(2026, 8, day), billed_amount=Decimal(amount)
            )

        def step(claim, action, actor, **data):
            return services.transition(
                claim_id=claim.pk, action=action, actor=actor,
                expected_version=claim.version, data=data or None,
            )

        def registered(claim):
            Claim.objects.filter(pk=claim.pk).update(submission_id=SEED_SUBMISSION_ID)
            claim.refresh_from_db()
            return claim

        draft("Acme Health", 1, "250.00")
        draft("Blue Ridge Mutual", 2, "1200.00")

        step(draft("Acme Health", 3, "300.00"), "submit", sam)  # SUBMITTED, registering

        c = registered(step(draft("Blue Ridge Mutual", 4, "450.00"), "submit", sam))  # SUBMITTED, registered

        c = registered(step(draft("Cascade Care", 5, "900.00"), "submit", sam))
        step(c, "start_review", rita)  # UNDER_REVIEW

        c = registered(step(draft("Acme Health", 6, "175.00"), "submit", sam))
        c = step(c, "start_review", rob)
        step(c, "request_info", rob, note="Please attach the operative report.")  # INFO_REQUESTED

        c = registered(step(draft("Cascade Care", 7, "2000.00"), "submit", sam))
        c = step(c, "start_review", rita)
        step(c, "approve", rita, approved_amount=Decimal("1800.00"))  # APPROVED

        c = registered(step(draft("Blue Ridge Mutual", 8, "640.00"), "submit", sam))
        c = step(c, "start_review", rob)
        step(c, "deny", rob, denial_reason="out_of_network")  # DENIED

        step(draft("Acme Health", 9, "80.00"), "withdraw", sam)  # WITHDRAWN

        self.stdout.write(f"claims: {Claim.objects.count()} created")
```

Note: `services.transition` receives `data=data or None` and `approved_amount` as a `Decimal`; the service's `_jsonable` stringifies it for the event.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q`. Expected: all pass.

- [ ] **Step 5: Seed on container start**

`backend/entrypoint.sh`:

```sh
#!/bin/sh
set -e
python manage.py migrate --noinput
python manage.py seed
exec "$@"
```

Verify: `docker compose up --build -d` from the repo root, then `docker compose logs api | grep -E "users:|claims:"`. Expected lines `users: sam, rita, rob` and `claims: 9 created`. Then `docker compose down`.

- [ ] **Step 6: Commit**

```bash
git add backend/claims/management backend/claims/tests/test_seed.py backend/entrypoint.sh
git commit -m "Seed users and sample claims on startup

One submitter and two reviewers with a shared demo password, and nine
claims covering every state, built through the service layer so each
carries a real history. Idempotent, so restarts do not duplicate."
```

---

### Task 5: Auth and claim API

**Files:**
- Create: `backend/claims/api/serializers.py`
- Modify: `backend/claims/api/views.py`, `backend/claims/api/urls.py`
- Create: `backend/claims/tests/test_api.py`

**Interfaces:**
- Consumes: services, transitions, models.
- Produces: `POST /api/auth/login/`, `POST /api/auth/logout/`, `GET /api/me/`, `GET /api/claims/?state=`, `POST /api/claims/`, `GET /api/claims/{id}/`, `PATCH /api/claims/{id}/`, `GET /api/claims/{id}/history/`. Detail payload includes `available_actions` and `registration`. `ClaimViewSet` is extended by Task 6 with the `transition` action.

- [ ] **Step 1: Write the failing tests**

`backend/claims/tests/test_api.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest claims/tests/test_api.py -q`. Expected: 404s on every route.

- [ ] **Step 3: Serializers**

`backend/claims/api/serializers.py`:

```python
from datetime import date

from django.utils import timezone
from rest_framework import serializers

from claims import transitions
from claims.models import Claim, ClaimEvent, User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "role"]


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)


class ClaimListSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = Claim
        fields = [
            "id", "reference", "payer", "service_date", "billed_amount",
            "state", "version", "created_by", "created_at", "updated_at",
        ]
        read_only_fields = fields


class ClaimDetailSerializer(ClaimListSerializer):
    available_actions = serializers.SerializerMethodField()
    registration = serializers.SerializerMethodField()

    class Meta(ClaimListSerializer.Meta):
        fields = ClaimListSerializer.Meta.fields + [
            "approved_amount", "denial_reason", "submission_id",
            "available_actions", "registration",
        ]
        read_only_fields = fields

    def get_available_actions(self, claim):
        user = self.context["request"].user
        today: date = timezone.localdate()
        return [
            {
                "action": a.transition.action,
                "label": a.transition.label,
                "fields": [
                    {"name": f.name, "type": f.type, "choices": list(f.choices)}
                    for f in a.transition.fields
                ],
                "blocked_reason": a.blocked_reason,
            }
            for a in transitions.available_actions(claim, user.role, today)
        ]

    def get_registration(self, claim):
        # Stage 1 shape. Stage 2 backs this with the registration outbox row.
        if claim.state == "DRAFT":
            return {"status": "not_submitted"}
        if claim.submission_id:
            return {"status": "registered", "submission_id": claim.submission_id}
        return {"status": "pending"}


class ClaimWriteSerializer(serializers.ModelSerializer):
    """Create and edit drafts. Business rules (date not in the future,
    amount > 0) are checked at submit, so a draft may be incomplete."""

    class Meta:
        model = Claim
        fields = ["payer", "service_date", "billed_amount"]
        extra_kwargs = {
            "payer": {"required": False},
            "service_date": {"required": False},
            "billed_amount": {"min_value": 0},
        }


class ClaimEventSerializer(serializers.ModelSerializer):
    actor = serializers.CharField(source="actor.username", read_only=True, default=None)

    class Meta:
        model = ClaimEvent
        fields = ["id", "action", "from_state", "to_state", "actor", "data", "severity", "created_at"]
        read_only_fields = fields
```

- [ ] **Step 4: Views and routes**

Replace `backend/claims/api/views.py` with:

```python
from django.contrib.auth import authenticate, login, logout
from django.db import connection
from django.middleware.csrf import get_token
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from claims import services
from claims.models import Claim, Role

from .serializers import (
    ClaimDetailSerializer,
    ClaimEventSerializer,
    ClaimListSerializer,
    ClaimWriteSerializer,
    LoginSerializer,
    UserSerializer,
)


class HealthView(APIView):
    """Liveness plus a database round trip. Unauthenticated on purpose:
    compose and humans use it to know the stack is up."""

    permission_classes = [AllowAny]

    def get(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return Response({"status": "ok", "database": "ok"})


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(request, **serializer.validated_data)
        if user is None:
            return Response({"detail": "Invalid username or password."}, status=status.HTTP_400_BAD_REQUEST)
        login(request, user)
        get_token(request)  # ensure the CSRF cookie is set for the SPA
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        get_token(request)
        return Response(UserSerializer(request.user).data)


class ClaimViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Claims as the current user may see them. Submitters see their own
    (D8); reviewers see all. Writes go through services; this layer only
    maps outcomes to HTTP."""

    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = Claim.objects.select_related("created_by")
        if self.request.user.role == Role.SUBMITTER:
            qs = qs.filter(created_by=self.request.user)
        state = self.request.query_params.get("state")
        if state:
            qs = qs.filter(state=state)
        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return ClaimListSerializer
        if self.action in ("create", "partial_update"):
            return ClaimWriteSerializer
        return ClaimDetailSerializer

    def _detail(self, claim, status_code=status.HTTP_200_OK):
        return Response(ClaimDetailSerializer(claim, context=self.get_serializer_context()).data, status=status_code)

    def create(self, request, *args, **kwargs):
        serializer = ClaimWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            claim = services.create_draft(created_by=request.user, **serializer.validated_data)
        except services.NotAllowed as exc:
            raise PermissionDenied(str(exc))
        return self._detail(claim, status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        claim = self.get_object()
        serializer = ClaimWriteSerializer(claim, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            claim = services.update_draft(claim=claim, actor=request.user, **serializer.validated_data)
        except services.NotAllowed as exc:
            return Response({"detail": str(exc)}, status=exc.status_code)
        return self._detail(claim)

    def update(self, request, *args, **kwargs):
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        claim = self.get_object()
        events = claim.events.select_related("actor").all()
        return Response(ClaimEventSerializer(events, many=True).data)
```

Replace `backend/claims/api/urls.py` with:

```python
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ClaimViewSet, HealthView, LoginView, LogoutView, MeView

router = DefaultRouter()
router.register("claims", ClaimViewSet, basename="claim")

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("", include(router.urls)),
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest -q`. Expected: all pass. If `DELETE .../history/` returns 405 via the router, the last assertion holds; if it returns 404, change `http_method_names` handling so that the `history` action only accepts GET (it already does through `methods=["get"]`), and confirm the router yields 405.

- [ ] **Step 6: Commit**

```bash
git add backend/claims/api backend/claims/tests/test_api.py
git commit -m "Add session login and the claim API

Login, logout and me over Django sessions with the CSRF cookie exposed
for the SPA. Claims list with a state filter, draft create and edit,
detail with the available-actions list computed from the transition
table for the current user, and a read-only history. Submitters are
scoped to their own claims in the queryset, so others' claims are 404."
```

---

### Task 6: Transition endpoint and concurrency

**Files:**
- Modify: `backend/claims/api/serializers.py`, `backend/claims/api/views.py`
- Create: `backend/claims/tests/test_concurrency.py`
- Modify: `backend/claims/tests/test_api.py` (append one test)

**Interfaces:**
- Consumes: `services.transition` and its exceptions; `ClaimViewSet`.
- Produces: `POST /api/claims/{id}/transition/` with body `{action, version, data}`; 409 body `{detail, current_state, current_version, last_event}`.

- [ ] **Step 1: Write the failing tests**

`backend/claims/tests/test_concurrency.py`:

```python
"""Requirement 4: two reviewers act at once, exactly one succeeds.
The thread test is the real race under a row lock; the API test is the
stale screen, which is the common case in practice (D5)."""

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
```

Append to `backend/claims/tests/test_api.py`:

```python
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

    bad_decimal = api.post(url, {"action": "approve", "version": 0, "data": {"approved_amount": "lots"}}, format="json")
    assert bad_decimal.status_code == 400

    ok = api.post(url, {"action": "withdraw", "version": 0}, format="json")
    assert ok.status_code == 200 and ok.json()["state"] == "WITHDRAWN"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest claims/tests/test_concurrency.py claims/tests/test_api.py -q`. Expected: 404 on the transition route; the thread test fails on `outcomes` being both "ok" only if the service were wrong, but it should pass already since the service is complete. Confirm which fail.

- [ ] **Step 3: Transition serializer**

Append to `backend/claims/api/serializers.py`:

```python
from decimal import Decimal, InvalidOperation


class TransitionSerializer(serializers.Serializer):
    """Envelope for POST /claims/{id}/transition/. Coerces the data fields
    the transition declares (decimal strings to Decimal); the rule in the
    transition table does the rest."""

    action = serializers.CharField()
    version = serializers.IntegerField(min_value=0)
    data = serializers.DictField(required=False, default=dict)

    def validate(self, attrs):
        t = transitions.TRANSITIONS.get(attrs["action"])
        if t is None:
            return attrs  # the service answers with a 400 and a message
        data = dict(attrs["data"])
        for f in t.fields:
            if f.type == "decimal" and f.name in data and data[f.name] is not None:
                try:
                    data[f.name] = Decimal(str(data[f.name]))
                except InvalidOperation:
                    raise serializers.ValidationError({f.name: "Must be a decimal number."})
        attrs["data"] = data
        return attrs
```

- [ ] **Step 4: Transition action on the viewset**

In `backend/claims/api/views.py`, add `TransitionSerializer` to the serializers import, and add this method to `ClaimViewSet` after `history`:

```python
    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        claim = self.get_object()  # 404 for claims outside the user's scope
        serializer = TransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        try:
            claim = services.transition(
                claim_id=claim.pk,
                action=payload["action"],
                actor=request.user,
                expected_version=payload["version"],
                data=payload["data"],
            )
        except services.ConflictError as exc:
            return Response(self._conflict(exc.claim), status=status.HTTP_409_CONFLICT)
        except services.RuleViolation as exc:
            return Response({"detail": str(exc), "errors": exc.errors}, status=status.HTTP_400_BAD_REQUEST)
        except services.NotAllowed as exc:
            return Response({"detail": str(exc)}, status=exc.status_code)
        return self._detail(claim)

    def _conflict(self, claim):
        last = claim.events.select_related("actor").order_by("-created_at", "-id").first()
        return {
            "detail": "This claim was changed by someone else. Reload to see the current state.",
            "current_state": claim.state,
            "current_version": claim.version,
            "last_event": ClaimEventSerializer(last).data if last else None,
        }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest -q`. Expected: all pass, including the threaded test.

- [ ] **Step 6: Commit**

```bash
git add backend/claims/api backend/claims/tests
git commit -m "Add the transition endpoint with conflict responses

POST /claims/{id}/transition/ carries the action, the version the client
rendered, and any input. Rule failures return field errors, wrong roles
403, and a stale version 409 with the current state and the last event
so the UI can say who did what. A two-thread test proves exactly one of
two concurrent reviewers succeeds."
```

---

### Task 7: Stage 1 notes and spec closure

**Files:**
- Create: `NOTES.md`
- Modify: `docs/specs/2026-09-12-stage-1-backend-core.md`, `docs/architecture/WORKFLOWS.md`, `README.md`

- [ ] **Step 1: Write NOTES.md with the stage 1 section**

`NOTES.md`:

```markdown
# Notes

## Stage 1: backend core

**Assumptions.** Submitters see and act on their own claims only; reviewers
see all. A draft may be created incomplete and edited (PATCH) until
submitted; the submit rules are checked at submit. Denial reasons are a
five-value fixed list standing in for standard adjustment reason codes.
Service dates are compared against today in UTC.

**Decisions.** The lifecycle is one declarative table (`transitions.py`, no
Django imports) read by both enforcement and the available-actions list,
so they cannot drift. Every state change runs in `services.transition`
under `select_for_update` plus a version check, and writes its audit
event in the same transaction; a stale client gets 409 with the current
state and the last event. History is append-only at the model and by a
Postgres trigger. Session auth, Django defaults only. Full rationale and
rejected alternatives: `docs/architecture/DECISIONS.md`.

**Tests.** Table-driven, one file per requirement proved: the transition
matrix (every action × state × role), rule cases, a two-thread race
against real Postgres, trigger immutability, and a handful of HTTP paths.

**Unfinished after stage 1.** Clearinghouse registration (stage 2) and
the frontend (stage 3). `start_review` is blocked until stage 2 stamps
a submission ID; the seed stamps one directly where a sample needs it.

**AI use.** Design was discussed with an AI assistant and recorded in
`docs/`; implementation followed a written plan with a subagent per task
and a review after each. Every line was read and is defended by the
author.
```

- [ ] **Step 2: Close the spec and correct W2**

In `docs/specs/2026-09-12-stage-1-backend-core.md`: change the status line to `Status: complete.`, tick every cut `- [x]`, and add `PATCH /api/claims/{id}/  {payer?, service_date?, billed_amount?}  drafts only` to the API block.

In `docs/architecture/WORKFLOWS.md` under W2, replace the line
`- ✗ unknown action / wrong from-state / wrong role → 409 or 403` with
`- ✗ wrong role → 403 · unknown action / wrong from-state → 400`.

- [ ] **Step 3: README logins**

Append to `README.md` under "Run":

```markdown
Seeded logins (password `password`): `sam` (submitter), `rita` and `rob` (reviewers).
```

- [ ] **Step 4: Commit**

```bash
git add NOTES.md docs README.md
git commit -m "Close stage 1: notes, spec status, workflow correction

NOTES.md records the stage 1 assumptions, decisions, tests and what is
left. The spec's cuts are ticked and its API block gains the draft edit
route. W2 now states the actual status codes."
```
