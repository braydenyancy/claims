from datetime import date
from decimal import Decimal, InvalidOperation

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
