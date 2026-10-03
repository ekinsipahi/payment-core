"""Enforcement helpers you call at Checkout-Session creation. They raise
``CardBlocked`` (a ValueError subclass) with a customer-safe message, so a view
that already maps ValueError -> HTTP 400 needs no change."""
from __future__ import annotations

from . import conf, email_reputation, risk
from .errors import CardBlocked


def card_risk_gate(user, *, client_ip=None, email=None) -> None:
    """Pre-Checkout gate for card top-ups: refuse disposable-email accounts, a
    random-looking email on a brand-new account, and any identity still inside its
    failed-attempt cooldown. Call BEFORE creating the Stripe/Paddle session.
    Crypto must NOT be gated (no chargeback to abuse) — every error nudges the
    abuser there.

    Also remembers (email, client_ip) for record_card_failure to recall later
    — see risk.remember_checkout_ip. Harmless for products that pass their own
    ip= explicitly at failure time (e.g. via a Payment.raw column); for ones
    that don't have anywhere else to carry the IP, this is what makes the
    failure webhook's IP-based cooldown/gold-signal keys work at all."""
    email = email or getattr(user, "email", "") or ""
    if client_ip and email:
        risk.remember_checkout_ip(email, client_ip)
    if risk.is_disposable_email(email):
        raise CardBlocked(
            "Card payments need a permanent email address. Use your main email, "
            "or pay with crypto for an instant top-up."
        )
    if email_reputation.random_new_email_blocks_card(email, user):
        raise CardBlocked(
            "We couldn't verify this account for card payments yet. Pay with "
            "crypto for an instant top-up, or try a card again a bit later."
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
