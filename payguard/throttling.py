"""DRF rate throttles for the top-up endpoints — the first server-side wall
against card-testing spam. Add to your top-up views' ``throttle_classes`` and
define the matching rates in DEFAULT_THROTTLE_RATES (see docs/INTEGRATION.md).

All throttles fail open if the cache is down (DRF's SimpleRateThrottle allows the
request when it can't read the history), so a cache blip never blocks real
top-ups."""
from __future__ import annotations

from rest_framework.throttling import SimpleRateThrottle

from .utils import client_ip


class _ClientIPThrottle(SimpleRateThrottle):
    """Keyed on the REAL client IP (left-most X-Forwarded-For), not the account —
    so a bot cycling throwaway accounts from one IP still hits a wall."""

    def get_cache_key(self, request, view):
        ident = client_ip(request) or "0.0.0.0"
        return self.cache_format % {"scope": self.scope, "ident": ident}


class TopupIPThrottle(_ClientIPThrottle):
    """Per-IP cap across ALL top-up creation (crypto + card). Rate: ``topup_ip``."""

    scope = "topup_ip"


class CardTopupIPThrottle(_ClientIPThrottle):
    """Tighter per-IP cap for card top-ups (the fraud vector). Rate: ``card_ip``."""

    scope = "card_ip"


class CardTopupUserThrottle(SimpleRateThrottle):
    """Per-account cap for card top-ups — tighter than the generic payment scope.
    Rate: ``card``."""

    scope = "card"

    def get_cache_key(self, request, view):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": user.pk}
