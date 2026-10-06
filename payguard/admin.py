"""Django admin for payguard's own tables. A host project only needs
``payguard`` in ``INSTALLED_APPS`` — Django's admin autodiscovery imports this
module automatically, so CardAttempt/CardCooldown show up with no admin.py code
of the host's own (and three products registering the same models separately
was exactly the duplication payguard replaced)."""
from django.contrib import admin

from .models import CardAttempt, CardCooldown


@admin.register(CardAttempt)
class CardAttemptAdmin(admin.ModelAdmin):
    """Append-only log of every failed (or fraud-blocked) card attempt — the
    card-testing/carding audit trail and dispute evidence. Only Stripe's safe
    fingerprint is stored, never a card number."""
    list_display    = ["created_at", "email", "ip", "fingerprint", "user", "outcome"]
    list_filter     = ["outcome", "created_at"]
    search_fields   = ["email", "ip", "fingerprint", "user__email"]
    ordering        = ["-created_at"]
    readonly_fields = [f.name for f in CardAttempt._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(CardCooldown)
class CardCooldownAdmin(admin.ModelAdmin):
    """One row per (kind, key). ``blocked_until`` in the future refuses a new
    card attempt from that account/IP/email/fingerprint; delete the row to
    unblock a false positive.

    ``permanent`` is the fraudster list: unlike the ladder it never decays and
    a later successful payment never clears it — only deleting the row, or
    un-ticking this box and saving, lifts it. Ticking it directly in admin
    also works: blocked_until is pushed ~100 years out automatically (see
    CardCooldown.save)."""
    list_display    = ["kind", "key", "permanent", "fail_count", "blocked_until",
                       "last_fail_at", "reason"]
    list_filter     = ["kind", "permanent"]
    search_fields   = ["key", "reason"]
    ordering        = ["-permanent", "-last_fail_at"]
    actions         = ["lift_block"]

    @admin.action(description="Lift block (delete selected cooldown rows)")
    def lift_block(self, request, queryset):
        count = queryset.count()
        queryset.delete()
        self.message_user(request, f"{count} cooldown row(s) cleared.")
