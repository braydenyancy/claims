from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.db import connection
from django.db.models import Count
from django.middleware.csrf import get_token
from django.utils.module_loading import import_string
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from claims import services, transitions
from claims.models import Claim, DenialReason, RegistrationStatus, Role, State

from .serializers import (
    AcknowledgeSerializer,
    ClaimDetailSerializer,
    ClaimEventSerializer,
    ClaimListSerializer,
    ClaimWriteSerializer,
    LoginSerializer,
    TransitionSerializer,
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


# How the UI should colour a value. Presentation, decided here so the
# frontend never has to know a state name (D4). The vocabulary is closed:
# neutral, info, success, warning, danger.
STATE_TONES = {
    State.DRAFT: "neutral",
    State.SUBMITTED: "info",
    State.UNDER_REVIEW: "info",
    State.INFO_REQUESTED: "warning",
    State.APPROVED: "success",
    State.DENIED: "danger",
    State.WITHDRAWN: "neutral",
}
REGISTRATION_TONES = {
    RegistrationStatus.PENDING: "neutral",
    RegistrationStatus.IN_FLIGHT: "info",
    RegistrationStatus.UNCERTAIN: "warning",
    RegistrationStatus.DONE: "success",
    RegistrationStatus.FAILED: "danger",
    RegistrationStatus.HALTED: "danger",
}


def _options(choices, tones, lower=False):
    return [
        {"value": v.lower() if lower else v, "label": label, "tone": tones.get(v, "neutral")}
        for v, label in choices
    ]


class MetaView(APIView):
    """The closed lists the UI needs for filters and labels. The UI
    renders these; it never decides anything from them."""

    def get(self, request):
        return Response(
            {
                "states": _options(State.choices, STATE_TONES),
                "denial_reasons": _options(DenialReason.choices, {}),
                "registration_statuses": _options(RegistrationStatus.choices, REGISTRATION_TONES, lower=True),
            }
        )


class ClaimViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Claims as the current user may see them. Submitters see their own;
    reviewers see all. Writes go through services; this layer only
    maps outcomes to HTTP."""

    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = Claim.objects.select_related("created_by", "registration")
        if self.request.user.role == Role.SUBMITTER:
            qs = qs.filter(created_by=self.request.user)
        if self.action == "list":
            state = self.request.query_params.get("state")
            if state:
                if state not in State.values:
                    raise ValidationError({"state": "Unknown state."})
                qs = qs.filter(state=state)
            alert = self.request.query_params.get("alert")
            if alert:
                if alert != "open":
                    raise ValidationError({"alert": "Only 'open' is supported."})
                qs = qs.filter(has_open_alert=True)
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
            return Response({"detail": str(exc), "errors": {}}, status=exc.status_code)
        return self._detail(claim, status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        claim = self.get_object()
        serializer = ClaimWriteSerializer(claim, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            claim = services.update_draft(claim=claim, actor=request.user, **serializer.validated_data)
        except services.NotAllowed as exc:
            return Response({"detail": str(exc), "errors": {}}, status=exc.status_code)
        return self._detail(claim)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Counts per state over the claims this user may see, ignoring
        the list filters, so the dashboard strip stays whole while the
        table is narrowed."""
        qs = self.get_queryset()
        counts = {row["state"]: row["count"] for row in qs.values("state").annotate(count=Count("id"))}
        return Response(
            {
                "total": sum(counts.values()),
                "open_alerts": qs.filter(has_open_alert=True).count(),
                "states": [dict(option, count=counts.get(option["value"], 0)) for option in _options(State.choices, STATE_TONES)],
            }
        )

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        claim = self.get_object()
        events = claim.events.select_related("actor").all()
        return Response(ClaimEventSerializer(events, many=True).data)

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        claim = self.get_object()  # 404 for claims outside the user's scope
        serializer = TransitionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "detail": "Invalid transition request.",
                    "errors": {k: " ".join(str(m) for m in v) for k, v in serializer.errors.items()},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
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
            return Response({"detail": str(exc), "errors": {}}, status=exc.status_code)
        return self._detail(claim)

    @action(detail=True, methods=["post"], url_path="registration/retry")
    def retry_registration(self, request, pk=None):
        claim = self.get_object()
        try:
            claim = services.retry_registration(claim=claim, actor=request.user)
        except services.NotAllowed as exc:
            return Response({"detail": str(exc), "errors": {}}, status=exc.status_code)
        return self._detail(claim)

    @action(detail=True, methods=["post"], url_path="registration/reconcile")
    def reconcile_registration(self, request, pk=None):
        claim = self.get_object()
        gateway = import_string(settings.CLEARINGHOUSE["GATEWAY"])()
        try:
            claim = services.reconcile_registration(claim=claim, actor=request.user, gateway=gateway)
        except services.NotAllowed as exc:
            return Response({"detail": str(exc), "errors": {}}, status=exc.status_code)
        except services.ClearinghouseUnavailable as exc:
            return Response({"detail": str(exc), "errors": {}}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return self._detail(claim)

    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        claim = self.get_object()
        serializer = AcknowledgeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"detail": "Invalid request.", "errors": {k: " ".join(str(m) for m in v) for k, v in serializer.errors.items()}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            claim = services.acknowledge_alert(claim=claim, actor=request.user, **serializer.validated_data)
        except services.RuleViolation as exc:
            return Response({"detail": str(exc), "errors": exc.errors}, status=status.HTTP_400_BAD_REQUEST)
        except services.NotAllowed as exc:
            return Response({"detail": str(exc), "errors": {}}, status=exc.status_code)
        return self._detail(claim)

    def _conflict(self, claim):
        # Only transitions and draft edits increment the claim's version.
        # A later registration or alert event must not be credited as the
        # change that caused this stale-write conflict.
        last = (
            claim.events.select_related("actor")
            .filter(action__in=[*transitions.TRANSITIONS, "edit"])
            .order_by("-created_at", "-id")
            .first()
        )
        return {
            "detail": "This claim was changed by someone else. Reload to see the current state.",
            "current_state": claim.state,
            "current_version": claim.version,
            "last_event": ClaimEventSerializer(last).data if last else None,
        }
