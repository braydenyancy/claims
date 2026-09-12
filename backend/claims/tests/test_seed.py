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
