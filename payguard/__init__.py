"""payguard — a free, open card-payment fraud pre-check for Django + Stripe.

A drop-in Django app that hardens Stripe (and Paddle) card top-ups against
**card-testing / stolen-card** abuse — the failed-attempt spam that quietly runs
up fees and trips Stripe's fraud thresholds. payguard is **product-agnostic**: it
never touches your wallet / credit / order logic. It answers one question —
*"should this card attempt be allowed, and what do we learn from its failures?"*

Public API (import from ``payguard``):
    is_disposable_email(email) -> bool
    looks_random_email(email) -> bool
    card_cooldown_remaining(user=, ip=, email=) -> int   # seconds; 0 = allowed
    record_card_failure(user=, ip=, email=, fingerprint=) -> None  # ip optional, see remember_checkout_ip
    permanently_block(user=, ip=, email=, fingerprint=, reason=) -> None  # the fraudster list
    is_permanently_blocked(user=, ip=, email=, fingerprint=) -> bool
    remember_checkout_ip(email, ip) -> None              # usually automatic via card_risk_gate
    card_wait_message(seconds) -> str
    card_risk_gate(user, client_ip=, email=)             # raises CardBlocked
    card_velocity_guard(open_sessions)                   # raises CardBlocked
    fingerprint_from_failed_pi(pi) -> str
    client_ip(request) -> str | None

See docs/ for the architecture, the Stripe dashboard checklist, and integration.
"""
from .email_reputation import looks_random_email, random_new_email_blocks_card
from .errors import CardBlocked
from .gates import card_risk_gate, card_velocity_guard
from .risk import (
    card_cooldown_remaining,
    card_wait_message,
    is_disposable_email,
    is_permanently_blocked,
    permanently_block,
    record_card_failure,
    record_card_success,
    remember_checkout_ip,
)
from .stripe_signals import fingerprint_from_failed_pi, is_uuid, sf
from .utils import client_ip

__all__ = [
    "CardBlocked",
    "is_disposable_email",
    "looks_random_email",
    "random_new_email_blocks_card",
    "card_cooldown_remaining",
    "record_card_failure",
    "record_card_success",
    "permanently_block",
    "is_permanently_blocked",
    "remember_checkout_ip",
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
