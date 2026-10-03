"""Card-payment risk layer: disposable-email scoring + an exponential, multi-key
cooldown after failed card payments, plus the multi-card "gold signal".

Enforced at Checkout-Session creation (the only thing a bot can spam on your
side, since Stripe hosts the card form). Failures are learned from Stripe's
``payment_intent.payment_failed`` webhook and recorded against EVERY identity the
attempt touched — account, client IP, email and Stripe card fingerprint — so a
bot that rotates one dimension still trips on the others. All functions fail
OPEN (a DB/logic error never blocks a real top-up)."""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from . import conf

logger = logging.getLogger("payguard")


def _ladder_seconds(fail_count: int) -> int:
    if fail_count <= 1:
        return 0
    return conf.COOLDOWN_LADDER.get(fail_count, conf.COOLDOWN_MAX)


# --- Disposable / throwaway email domains ----------------------------------
_DISPOSABLE_DOMAINS = {
    # Pulled from esimsterr's access log on launch day, not from a public list:
    # four accounts signed up on these and opened small card checkouts within
    # two minutes. Public disposable lists run to tens of thousands of stale
    # domains; the ones that actually turn up are worth more than all of them.
    "moimoi.re", "mailto.plus", "fexpost.com", "fexbox.org", "rover.info",
    "chitthi.in", "fextemp.com", "any.pink", "merepost.com",

    "mailinator.com", "yopmail.com", "guerrillamail.com", "guerrillamail.info",
    "sharklasers.com", "grr.la", "10minutemail.com", "10minutemail.net",
    "tempmail.com", "temp-mail.org", "tempmailo.com", "throwawaymail.com",
    "trashmail.com", "getnada.com", "nada.email", "maildrop.cc", "dispostable.com",
    "fakeinbox.com", "mailnesia.com", "mohmal.com", "emailondeck.com",
    "spam4.me", "tmpmail.org", "tmpmail.net", "mintemail.com", "mailcatch.com",
    "moakt.com", "mytemp.email", "burnermail.io", "33mail.com", "inboxkitten.com",
    "temp-mail.io", "tempr.email", "dropmail.me", "harakirimail.com",
    "maileanator.com", "spambog.com", "vomoto.com", "tempinbox.com",
}


def is_disposable_email(email: str) -> bool:
    """True if the email's domain is a known disposable/throwaway provider.
    Extend the built-in set via the DISPOSABLE_EMAIL_DOMAINS setting."""
    if not email or "@" not in email:
        return False
    domain = email.rsplit("@", 1)[-1].strip().lower()
    if not domain:
        return False
    return domain in _DISPOSABLE_DOMAINS or domain in conf.extra_disposable_domains()


# --- Multi-key exponential cooldown ----------------------------------------
# Providers that ignore dots in the local part: one inbox, many spellings.
_DOT_BLIND = {"gmail.com", "googlemail.com"}
_DOMAIN_ALIASES = {"googlemail.com": "gmail.com"}


def canonical_email(email: str) -> str:
    """The inbox an address actually reaches, for use as a counting key.

    Plus-addressing is universal and Gmail ignores dots, so one mailbox can
    present an unbounded number of distinct-looking addresses. Counted
    literally, every spelling is a fresh identity with a clean record — the
    cheapest evasion there is, and one that turned up in esimsterr's live
    traffic on the first day as ``d.a.w.di2153azdin@gmail.com``.

    Only ever a key. The address the customer typed is what the product stores
    and emails; this decides nothing except whether two attempts came from the
    same place.

    Dots are collapsed **only** for the providers that ignore them. Doing it
    everywhere would merge two strangers at Outlook into one identity and
    punish both for each other's cards.
    """
    address = (email or "").strip().lower()
    if "@" not in address:
        return address
    local, _, domain = address.rpartition("@")
    domain = _DOMAIN_ALIASES.get(domain, domain)
    local = local.split("+", 1)[0]
    if domain in _DOT_BLIND:
        local = local.replace(".", "")
    return f"{local}@{domain}" if local else address


def _keys(user=None, ip=None, email=None, fingerprint=None):
    from .models import CardCooldown

    out = []
    if user is not None and getattr(user, "pk", None):
        out.append((CardCooldown.Kind.ACCOUNT, str(user.pk)))
    if ip:
        out.append((CardCooldown.Kind.IP, str(ip)[:255]))
    if email and "@" in email:
        out.append((CardCooldown.Kind.EMAIL, canonical_email(email)[:255]))
    if fingerprint:
        out.append((CardCooldown.Kind.FINGERPRINT, str(fingerprint)[:255]))
    return out


def _force_block(kind, key, now, seconds: int) -> None:
    """Push a key's cooldown to AT LEAST now+seconds (never shortens it).

    An IP serves a fraction of what an account serves -- see
    conf.ip_cooldown_factor for why. Applied here rather than at each call site
    so that every route to an address block, the ladder and the multi-card
    penalty alike, is softened the same way and none can be added later that
    forgets to.
    """
    from .models import CardCooldown

    if not key or seconds <= 0:
        return
    if kind == CardCooldown.Kind.IP:
        seconds = int(seconds * conf.ip_cooldown_factor())
        if seconds <= 0:
            return
    target = now + timezone.timedelta(seconds=seconds)
    try:
        with transaction.atomic():
            row, _ = CardCooldown.objects.select_for_update().get_or_create(kind=kind, key=key)
            if row.last_fail_at is None:
                row.first_fail_at = row.first_fail_at or now
            row.last_fail_at = now
            if row.blocked_until is None or row.blocked_until < target:
                row.blocked_until = target
            row.save()
    except Exception:  # noqa: BLE001
        logger.exception("_force_block failed for %s:%s", kind, key)


def _multicard_penalty(user, ip, now) -> None:
    """The gold signal: one account trying several DIFFERENT cards in minutes.
    Count distinct failed fingerprints for this account in the window; once it
    crosses the threshold, slam a long cooldown on the account (and the IP) —
    base minutes, doubling per extra card, capped at 6 hours."""
    from .models import CardAttempt, CardCooldown

    if user is None or not getattr(user, "pk", None):
        return
    threshold = conf.distinct_fingerprints()
    window = conf.distinct_window_min()
    base_min = conf.multicard_base_min()
    if threshold <= 0 or window <= 0 or base_min <= 0:
        return
    try:
        since = now - timezone.timedelta(minutes=window)
        distinct = (
            CardAttempt.objects.filter(user=user, created_at__gte=since, outcome="failed")
            .exclude(fingerprint="")
            .values("fingerprint")
            .distinct()
            .count()
        )
    except Exception:  # noqa: BLE001
        logger.exception("_multicard_penalty count failed")
        return
    if distinct < threshold:
        return
    minutes = min(base_min * (2 ** (distinct - threshold)), 360)
    secs = minutes * 60
    _force_block(CardCooldown.Kind.ACCOUNT, str(user.pk), now, secs)
    if ip:
        _force_block(CardCooldown.Kind.IP, str(ip)[:255], now, secs)
    logger.warning("multicard penalty: user=%s distinct_cards=%s cooldown=%smin",
                   user.pk, distinct, minutes)


def record_card_failure(*, user=None, ip=None, email=None, fingerprint=None) -> None:
    """Register a failed card payment: log the attempt, bump the per-key ladder
    for every identity it touched, then apply the multi-card penalty if this
    account is burning distinct cards. Never raises."""
    from .models import CardAttempt, CardCooldown

    now = timezone.now()
    try:
        CardAttempt.objects.create(
            user=user if (user is not None and getattr(user, "pk", None)) else None,
            fingerprint=(str(fingerprint)[:255] if fingerprint else ""),
            ip=(str(ip)[:255] if ip else ""),
            email=((email or "").strip().lower()[:255]),
            outcome="failed",
        )
    except Exception:  # noqa: BLE001
        logger.exception("CardAttempt log failed")

    decay_before = now - timezone.timedelta(hours=conf.DECAY_HOURS)
    for kind, key in _keys(user=user, ip=ip, email=email, fingerprint=fingerprint):
        try:
            with transaction.atomic():
                row, _ = CardCooldown.objects.select_for_update().get_or_create(kind=kind, key=key)
                if row.last_fail_at and row.last_fail_at < decay_before:
                    row.fail_count = 0
                    row.first_fail_at = None
                row.fail_count = (row.fail_count or 0) + 1
                if row.first_fail_at is None:
                    row.first_fail_at = now
                row.last_fail_at = now
                secs = _ladder_seconds(row.fail_count)
                row.blocked_until = now + timezone.timedelta(seconds=secs) if secs else None
                row.save()
        except Exception:  # noqa: BLE001
            logger.exception("record_card_failure failed for %s:%s", kind, key)

    _multicard_penalty(user, ip, now)


def card_cooldown_remaining(*, user=None, ip=None, email=None) -> int:
    """Seconds a new card attempt must wait — the MAX active cooldown across the
    account / IP / email keys (fingerprint is unknown until the card is entered
    on Stripe, so it can't gate session creation). 0 = allowed. Fails open."""
    from .models import CardCooldown

    keys = _keys(user=user, ip=ip, email=email)
    if not keys:
        return 0
    now = timezone.now()
    decay_before = now - timezone.timedelta(hours=conf.DECAY_HOURS)
    remaining = 0
    try:
        rows = {
            (r.kind, r.key): r
            for r in CardCooldown.objects.filter(
                kind__in=[k for k, _ in keys], key__in=[v for _, v in keys]
            )
        }
        for kind, key in keys:
            r = rows.get((kind, key))
            if not r or not r.blocked_until:
                continue
            if r.last_fail_at and r.last_fail_at < decay_before:
                continue
            if r.blocked_until > now:
                remaining = max(remaining, int((r.blocked_until - now).total_seconds()) + 1)
    except Exception:  # noqa: BLE001
        logger.exception("card_cooldown_remaining failed")
        return 0
    return remaining


def card_wait_message(seconds: int) -> str:
    """Human, non-leaky message for a cooldown block (never reveals which key)."""
    if seconds >= 3600:
        wait = "about an hour"
    elif seconds >= 60:
        wait = f"about {max(1, round(seconds / 60))} minute(s)"
    else:
        wait = f"{seconds} second(s)"
    return (
        f"Too many failed card attempts. Please wait {wait} before trying a card "
        "again — or pay with crypto for an instant top-up."
    )
