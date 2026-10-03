"""Version-proof readers for Stripe webhook objects + a helper to pull the card
fingerprint out of a failed PaymentIntent.

stripe-python 15's StripeObject is NOT a dict: no ``.get()``, and ``[...]`` raises
KeyError on a missing key. ``sf`` walks a path via subscript, falls back to
attribute access, and swallows the misses — so a Stripe version that ships a
StripeObject instead of a dict can't 500 your webhook."""
from __future__ import annotations

import uuid


def sf(obj, *path, default=None):
    """Read ``obj[path...]`` tolerating both plain dicts and Stripe StripeObjects."""
    cur = obj
    for key in path:
        if cur is None:
            return default
        try:
            cur = cur[key]
        except (KeyError, IndexError, TypeError):
            try:
                cur = getattr(cur, key)
            except AttributeError:
                return default
    return default if cur is None else cur


def is_uuid(val) -> bool:
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def fingerprint_from_failed_pi(pi) -> str:
    """Stripe's SAFE card fingerprint from a failed PaymentIntent (never the PAN).
    Tries ``last_payment_error`` first (reliable on a decline), then the charge."""
    return (
        sf(pi, "last_payment_error", "payment_method", "card", "fingerprint")
        or sf(pi, "charges", "data", 0, "payment_method_details", "card", "fingerprint")
        or ""
    )
