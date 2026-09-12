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
