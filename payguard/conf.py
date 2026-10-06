"""Tunable knobs, read from Django settings with safe defaults. Every value can
be overridden in the host project's settings (or via its env loader)."""
from django.conf import settings


def _get(name, default):
    return getattr(settings, name, default)


# --- Exponential cooldown ladder (failed card attempts) ---------------------
# fail_count -> cooldown seconds. First failure free, then 30s / 2m / 10m / 1h.
COOLDOWN_LADDER = {1: 0, 2: 30, 3: 120, 4: 600}
COOLDOWN_MAX = 3600
DECAY_HOURS = 24  # a quiet spell resets the per-key counter


# --- Permanent block (the "fraudster list") ----------------------------------
# Past this many failures on ONE key (account/IP/email/fingerprint) within a
# single non-decayed run, stop re-issuing ladder cooldowns and block that key
# forever instead. A real customer does not fail a card payment 8 times in a
# row without giving up or switching to crypto; something retrying past that
# point is scripted. Set to 0 to disable count-based escalation (Stripe Radar's
# explicit "fraudulent" signal still triggers permanently_block() directly,
# see stripe_signals / the host project's webhook handler).
def permanent_block_after():
    return int(_get("CARD_PERMANENT_BLOCK_AFTER", 8) or 0)


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
# An account is one person. An address often is not: travellers share one NAT
# address behind an airport / hotel / cruise-ship network, mobile carriers put
# thousands of subscribers behind one CGNAT address, and some products resell a
# shared exit address outright. Blocking such an IP for hours does not stop an
# attacker who can change address in seconds — it locks out the paying customers
# who can't, and they don't complain, they leave.
#
# So the address still counts (one machine grinding a list from one place does
# slow down), but at a fraction of an account's weight. The rules that actually
# catch a distributed attempt are the account ladder and the distinct-card
# signal, neither of which cares what address it came from.
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


# --- Random / brand-new email reputation ------------------------------------
# A random-looking local part ("x7f9qk2j8@...") on a brand-new account is a
# card-tester tell. Because legit users do sometimes have random-looking aliases,
# we only BLOCK card (push to crypto) when BOTH signals agree: random-looking AND
# the account is younger than CARD_NEW_ACCOUNT_MIN minutes. After that window the
# same account's card works normally. Set CARD_BLOCK_RANDOM_NEW_EMAIL=False to
# only score (never block), or CARD_NEW_ACCOUNT_MIN=0 to disable the age half.
def block_random_new_email():
    return bool(_get("CARD_BLOCK_RANDOM_NEW_EMAIL", True))


def new_account_min():
    return int(_get("CARD_NEW_ACCOUNT_MIN", 60) or 0)


def random_email_min_len():
    return int(_get("CARD_RANDOM_EMAIL_MIN_LEN", 10) or 0)


def random_email_digit_ratio():
    try:
        return float(_get("CARD_RANDOM_EMAIL_DIGIT_RATIO", 0.35))
    except (TypeError, ValueError):
        return 0.35
