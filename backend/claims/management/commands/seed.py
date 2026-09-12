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
