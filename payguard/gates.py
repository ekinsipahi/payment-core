"""Enforcement helpers you call at Checkout-Session creation. They raise
``CardBlocked`` (a ValueError subclass) with a customer-safe message, so a view
that already maps ValueError -> HTTP 400 needs no change."""
from __future__ import annotations

from . import conf, risk
from .errors import CardBlocked


def card_risk_gate(user, *, client_ip=None, email=None) -> None:
    """Pre-Checkout gate for card top-ups: refuse disposable-email accounts and
    any identity still inside its failed-attempt cooldown. Call BEFORE creating
    the Stripe/Paddle session. Crypto must NOT be gated (no chargeback to abuse)
    — the error message nudges the abuser there."""
    email = email or getattr(user, "email", "") or ""
    if risk.is_disposable_email(email):
        raise CardBlocked(
            "Card payments need a permanent email address. Use your main email, "
            "or pay with crypto for an instant top-up."
        )
    wait = risk.card_cooldown_remaining(user=user, ip=client_ip, email=email)
    if wait > 0:
        raise CardBlocked(risk.card_wait_message(wait), retry_after=wait)


def card_velocity_guard(open_sessions: int) -> None:
    """Block a new card session when the account already has too many UNCREDITED
    card payments open in the trailing window. ``open_sessions`` is a count the
    caller computes from its own Payment model, e.g.::

        from datetime import timedelta
        from django.utils import timezone
        since = timezone.now() - timedelta(minutes=settings.CARD_SESSION_WINDOW_MIN)
        n = Payment.objects.filter(user=user, provider=Payment.Provider.STRIPE,
                                   credited=False, created_at__gte=since).count()
        card_velocity_guard(n)

    Keeping the count in the caller leaves payguard decoupled from your Payment
    schema. A non-positive cap disables the guard."""
    cap = conf.max_open_sessions()
    if cap <= 0:
        return
    if open_sessions >= cap:
        raise CardBlocked(
            "Too many pending card payments. Finish an open checkout or wait a "
            "few minutes — or pay with crypto for an instant top-up."
        )
