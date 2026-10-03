"""Tunable knobs, read from Django settings with safe defaults. Every value can
be overridden in the host project's settings (or via its env loader). Keeping the
names identical to the Sterr backends makes payguard a drop-in replacement."""
from django.conf import settings


def _get(name, default):
    return getattr(settings, name, default)


# --- Exponential cooldown ladder (failed card attempts) ---------------------
# fail_count -> cooldown seconds. First failure free, then 30s / 2m / 10m / 1h.
COOLDOWN_LADDER = {1: 0, 2: 30, 3: 120, 4: 600}
COOLDOWN_MAX = 3600
DECAY_HOURS = 24  # a quiet spell resets the per-key counter


# --- Multi-card "gold signal" -----------------------------------------------
def distinct_fingerprints():
    return int(_get("CARD_DISTINCT_FINGERPRINTS", 3) or 0)


def distinct_window_min():
    return int(_get("CARD_DISTINCT_WINDOW_MIN", 30) or 0)


def multicard_base_min():
    return int(_get("CARD_MULTICARD_COOLDOWN_MIN", 30) or 0)


# --- Open-session velocity guard --------------------------------------------
def max_open_sessions():
    return int(_get("CARD_MAX_OPEN_SESSIONS", 3) or 0)


def session_window_min():
    return int(_get("CARD_SESSION_WINDOW_MIN", 10) or 0)


# --- Disposable email extension ---------------------------------------------
def extra_disposable_domains():
    try:
        extra = _get("DISPOSABLE_EMAIL_DOMAINS", None) or []
        return {d.strip().lower() for d in extra if d and d.strip()}
    except Exception:  # noqa: BLE001
        return set()
