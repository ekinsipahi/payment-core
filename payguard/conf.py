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


# --- Shared addresses --------------------------------------------------------
# How much of a cooldown an IP serves, as a fraction of what an account serves.
#
# An account is one person. An address is not, and for these products it is
# emphatically not: esimsterr sells to travellers, so an airport, a hotel and a
# cruise ship each put every customer behind one NAT address, and proxysterr
# sells the shared exit address itself. Blocking an IP for six hours there does
# not stop an attacker who can change address in seconds; it stops the paying
# customers who cannot.
#
# So the address still counts -- a single machine grinding through a list from
# one place does get slower -- but it counts at a quarter weight, and the rules
# that actually catch a distributed attempt are the account ladder and the
# distinct-card signal, neither of which cares what address it came from.
#
# Set to 1.0 for a product whose customers each have their own address.
def ip_cooldown_factor():
    try:
        return max(0.0, float(_get("CARD_IP_COOLDOWN_FACTOR", 0.25)))
    except (TypeError, ValueError):
        return 0.25


# --- Disposable email extension ---------------------------------------------
def extra_disposable_domains():
    try:
        extra = _get("DISPOSABLE_EMAIL_DOMAINS", None) or []
        return {d.strip().lower() for d in extra if d and d.strip()}
    except Exception:  # noqa: BLE001
        return set()
