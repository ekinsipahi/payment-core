"""payguard — shared card-payment fraud defense for the Sterr backends.

A drop-in Django app that hardens Stripe (and Paddle) card top-ups against
card-testing / stolen-card abuse, extracted from proxysterr so esimsterr and
linksterr can use the exact same layer. Product-agnostic: it never touches your
wallet/credit logic — it only decides whether a card attempt is allowed and
learns from failures.

Public API (import from ``payguard``):
    is_disposable_email(email) -> bool
    card_cooldown_remaining(user=, ip=, email=) -> int   # seconds; 0 = allowed
    record_card_failure(user=, ip=, email=, fingerprint=) -> None
    card_wait_message(seconds) -> str
    card_risk_gate(user, client_ip=, email=)             # raises CardBlocked
    card_velocity_guard(open_sessions)                   # raises CardBlocked
    fingerprint_from_failed_pi(pi) -> str
    client_ip(request) -> str | None

See docs/ for the architecture, the Stripe dashboard checklist, and integration.
"""
from .errors import CardBlocked
from .gates import card_risk_gate, card_velocity_guard
from .risk import (
    card_cooldown_remaining,
    card_wait_message,
    is_disposable_email,
    record_card_failure,
)
from .stripe_signals import fingerprint_from_failed_pi, is_uuid, sf
from .utils import client_ip

__all__ = [
    "CardBlocked",
    "is_disposable_email",
    "card_cooldown_remaining",
    "record_card_failure",
    "card_wait_message",
    "card_risk_gate",
    "card_velocity_guard",
    "fingerprint_from_failed_pi",
    "is_uuid",
    "sf",
    "client_ip",
]

default_app_config = "payguard.apps.PayguardConfig"
__version__ = "0.1.0"
