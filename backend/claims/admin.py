"""Read-only inspection of the data. Every write goes through the
service layer and the API; the admin is a window, not a door."""

from django.contrib import admin

from .models import Claim, ClaimEvent, Registration, User


class ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(ReadOnly):
    list_display = ("username", "role", "is_superuser")


@admin.register(Claim)
class ClaimAdmin(ReadOnly):
    list_display = ("reference", "payer", "state", "version", "billed_amount", "approved_amount", "has_open_alert", "created_by")
    list_filter = ("state", "has_open_alert")
    search_fields = ("reference", "payer")


@admin.register(ClaimEvent)
class ClaimEventAdmin(ReadOnly):
    list_display = ("created_at", "claim", "actor", "action", "from_state", "to_state", "severity")
    list_filter = ("severity", "action")
    ordering = ("-created_at", "-id")


@admin.register(Registration)
class RegistrationAdmin(ReadOnly):
    list_display = ("claim", "status", "attempts", "next_attempt_at", "last_error")
    list_filter = ("status",)
