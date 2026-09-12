from unittest.mock import patch

import pytest
from django.core.management import call_command

from claims import services
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


@pytest.mark.django_db(transaction=True)
def test_seed_is_all_or_nothing_when_interrupted():
    real_transition = services.transition
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("interrupted mid-seed")
        return real_transition(*args, **kwargs)

    with patch("claims.services.transition", side_effect=flaky):
        with pytest.raises(RuntimeError):
            call_command("seed")

    assert Claim.objects.count() == 0

    call_command("seed")
    assert Claim.objects.count() == 9
