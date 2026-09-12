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
