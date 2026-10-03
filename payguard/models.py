from django.conf import settings
from django.db import models


class CardCooldown(models.Model):
    """Exponential cooldown state for the card-testing guard, tracked PER identity
    dimension — account, client IP, email AND Stripe card fingerprint — so a bot
    rotating any one of them still trips on the others. A failed card payment
    (Stripe ``payment_intent.payment_failed``) bumps the fail count on every key
    it touches and pushes ``blocked_until`` out along the ladder (30s -> 2m ->
    10m -> 1h). A new card Checkout Session is refused while ANY of its keys is
    still blocked. The count decays after a quiet spell. We store Stripe's safe
    fingerprint, never a card number."""

    class Kind(models.TextChoices):
        ACCOUNT = "account", "Account"
        IP = "ip", "Client IP"
        EMAIL = "email", "Email"
        FINGERPRINT = "fingerprint", "Card fingerprint"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    key = models.CharField(max_length=255)  # user id / ip / lowercased email / fingerprint
    fail_count = models.PositiveIntegerField(default=0)
    blocked_until = models.DateTimeField(null=True, blank=True)
    first_fail_at = models.DateTimeField(null=True, blank=True)
    last_fail_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payguard_card_cooldowns"
        unique_together = (("kind", "key"),)
        indexes = [models.Index(fields=["kind", "key"])]

    def __str__(self):
        return f"CardCooldown({self.kind}:{self.key} x{self.fail_count} until {self.blocked_until})"


class CardAttempt(models.Model):
    """Append-only log of FAILED card attempts, one row per failure. Powers the
    strongest card-testing signal: a single account burning through several
    DIFFERENT cards (distinct Stripe fingerprints) in minutes — nothing a real
    customer does. Also an audit trail for disputes. Stripe fingerprint only,
    never a card number."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="payguard_card_attempts",
    )
    fingerprint = models.CharField(max_length=255, blank=True, db_index=True)
    ip = models.CharField(max_length=255, blank=True)
    email = models.CharField(max_length=255, blank=True)
    outcome = models.CharField(max_length=16, default="failed")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payguard_card_attempts"
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["fingerprint", "created_at"]),
        ]

    def __str__(self):
        return f"CardAttempt({self.email or self.user_id} {self.fingerprint[:10]} {self.outcome})"
