from datetime import date
from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from claims import transitions
from claims.models import Claim, ClaimEvent, Registration, RegistrationStatus, Role, Severity, State, User


class UserSerializer(serializers.ModelSerializer):
    can_create_claims = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "role", "can_create_claims"]

    def get_can_create_claims(self, user):
        return user.role == Role.SUBMITTER


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)


class ClaimListSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = Claim
        fields = [
            "id", "reference", "payer", "service_date", "billed_amount",
            "state", "version", "has_open_alert", "created_by", "created_at", "updated_at",
        ]
        read_only_fields = fields


class ClaimDetailSerializer(ClaimListSerializer):
    available_actions = serializers.SerializerMethodField()
    registration = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    alerts = serializers.SerializerMethodField()

    class Meta(ClaimListSerializer.Meta):
        fields = ClaimListSerializer.Meta.fields + [
            "approved_amount", "denial_reason", "submission_id",
            "available_actions", "registration", "can_edit", "alerts",
        ]
        read_only_fields = fields

    def get_can_edit(self, claim):
        user = self.context["request"].user
        return claim.state == State.DRAFT and claim.created_by_id == user.id

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
        user = self.context["request"].user
        try:
            reg = claim.registration
        except Registration.DoesNotExist:
            return {"status": "not_submitted", "can_retry": False, "can_reconcile": False}
        return {
            "status": reg.status.lower(),
            "attempts": reg.attempts,
            "last_error": reg.last_error,
            "submission_id": claim.submission_id,
            "next_attempt_at": reg.next_attempt_at.isoformat() if reg.status == "PENDING" else None,
            "can_retry": reg.status == RegistrationStatus.FAILED and user.role == Role.REVIEWER,
            "can_reconcile": reg.status == RegistrationStatus.UNCERTAIN and user.role == Role.REVIEWER,
        }

    def get_alerts(self, claim):
        """Every alert on the claim with its answer, oldest first. The client
        renders this; it never re-derives an acknowledgement from history."""
        user = self.context["request"].user
        events = list(
            claim.events.select_related("actor")
            .filter(Q(severity=Severity.ALERT) | Q(action="alert_acknowledged"))
            .order_by("created_at", "id")
        )
        # The same lookup services.acknowledge_alert uses: an acknowledgement
        # names the alert it answers in data.event_id.
        acks = {e.data.get("event_id"): e for e in events if e.action == "alert_acknowledged"}
        alerts = []
        for event in events:
            if event.severity != Severity.ALERT:
                continue
            ack = acks.get(event.id)
            alerts.append(
                {
                    "event_id": event.id,
                    "action": event.action,
                    "created_at": event.created_at.isoformat(),
                    "data": event.data,
                    "acknowledgement": None
                    if ack is None
                    else {
                        "actor": ack.actor.username if ack.actor else None,
                        "note": ack.data.get("note", ""),
                        "created_at": ack.created_at.isoformat(),
                    },
                    "can_acknowledge": user.role == Role.REVIEWER and ack is None,
                }
            )
        return alerts


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
                if not data[f.name].is_finite():
                    raise serializers.ValidationError({f.name: "Must be a decimal number."})
                try:
                    rounded = data[f.name].quantize(Decimal(1).scaleb(-f.decimal_places))
                except (InvalidOperation, ValueError):
                    raise serializers.ValidationError({f.name: "Must have at most two decimal places."})
                if data[f.name] != rounded or len(data[f.name].as_tuple().digits) > f.max_digits:
                    raise serializers.ValidationError({f.name: "Must have at most two decimal places."})
        attrs["data"] = data
        return attrs


class AcknowledgeSerializer(serializers.Serializer):
    event_id = serializers.IntegerField(min_value=1)
    note = serializers.CharField(allow_blank=True, trim_whitespace=False, max_length=2000)
