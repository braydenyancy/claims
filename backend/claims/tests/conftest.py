from datetime import date
from decimal import Decimal

import pytest

from claims.models import Claim, Role, User


@pytest.fixture
def submitter(db):
    return User.objects.create_user("sam", password="password", role=Role.SUBMITTER)


@pytest.fixture
def reviewer(db):
    return User.objects.create_user("rita", password="password", role=Role.REVIEWER)


@pytest.fixture
def reviewer2(db):
    return User.objects.create_user("rob", password="password", role=Role.REVIEWER)


@pytest.fixture
def claim(submitter):
    return Claim.objects.create(
        payer="Acme Health",
        service_date=date(2026, 9, 1),
        billed_amount=Decimal("100.00"),
        created_by=submitter,
    )
