"""Email reputation scoring for card top-ups.

Two signals beyond the disposable-domain blocklist (which lives in ``risk``):

1. **random-looking local part** — ``x7f9qk2j8@gmail.com`` is what a script that
   mints inboxes produces; a person's address rarely is.
2. **brand-new account** — the attempt lands minutes after signup.

Neither is damning alone (plenty of real people have alias-style addresses, and
new accounts pay too), so this module only recommends BLOCKING card when BOTH
agree. Everything is tunable; everything fails OPEN. Crypto is never affected —
the point is to deflect a likely card-tester to a rail with no chargeback, not to
turn anyone away."""
from __future__ import annotations

import logging
import unicodedata

from django.utils import timezone

from . import conf

logger = logging.getLogger("payguard")

# `y` counts. It is a full vowel in Polish, Czech, Welsh and Norwegian, and the
# test it feeds asks whether a string is pronounceable rather than whether it is
# English. Leaving it out flagged `krzysztofwszczyzna` -- a real Polish name --
# as machine-generated. It costs nothing in the other direction: gibberish is
# caught by the digit ratio or by having no vowels of any kind.
_VOWELS = set("aeiouy")

# Letters that carry a vowel but are not one of those five, folded so that a
# name written in its own alphabet scores the same as its transliteration.
#
# This matters more than it looks. The vowel test asks "is this consonant soup",
# and with an ASCII-only vowel set every non-ASCII vowel counts as a consonant --
# so `mehmetşükrüyıldırım` scored 2 vowels in 19 letters and was called
# machine-generated, while the same person writing `mehmetsukruyildirim` scored
# 7 and sailed through. A customer typing their own name in their own alphabet
# is the last person who should be refused a card.
#
# NFKD handles anything built from a base letter plus a combining mark (ü, ö, é,
# ñ). The map below is for the letters it cannot decompose because they are
# letters in their own right: Turkish dotless i, Scandinavian ø/æ/å, German ß,
# Polish ł, Croatian đ.
_FOLD = str.maketrans({
    "ı": "i", "ø": "o", "æ": "ae", "œ": "oe", "ß": "ss", "ł": "l", "đ": "d",
    "å": "a", "ð": "d", "þ": "th",
})


def _fold(text: str) -> str:
    """Strip diacritics so a vowel is still a vowel in any Latin alphabet."""
    decomposed = unicodedata.normalize("NFKD", text)
    bare = "".join(c for c in decomposed if not unicodedata.combining(c))
    return bare.translate(_FOLD)


def looks_random_email(email: str) -> bool:
    """Heuristic: does the local part look machine-generated? Conservative by
    design — tuned to fire on gibberish, not on a normal human alias. Signals:
    long + digit-heavy, or long + almost no vowels (consonant soup)."""
    if not email or "@" not in email:
        return False
    local = email.split("@", 1)[0].strip().lower()
    # Normalise the common, legitimate separators out before judging randomness,
    # and fold the alphabet so the test is about shape rather than about which
    # language the name is written in.
    core = _fold(local).replace(".", "").replace("_", "").replace("-", "").replace("+", "")
    if not core:
        return False
    min_len = conf.random_email_min_len()
    if len(core) < min_len:
        return False
    digits = sum(c.isdigit() for c in core)
    letters = [c for c in core if c.isalpha()]
    digit_ratio = digits / len(core)
    vowel_ratio = (sum(c in _VOWELS for c in letters) / len(letters)) if letters else 0.0
    # Digit-heavy medium string, or a longer string with almost no vowels.
    if digit_ratio >= conf.random_email_digit_ratio():
        return True
    if len(core) >= max(min_len, 14) and vowel_ratio < 0.20:
        return True
    return False


def account_is_new(user) -> bool:
    """True if the account was created inside the new-account window. Unknown /
    no ``date_joined`` → treated as NOT new (fail open — the age half is skipped
    and random-alone never blocks)."""
    minutes = conf.new_account_min()
    if minutes <= 0 or user is None:
        return False
    joined = getattr(user, "date_joined", None)
    if not joined:
        return False
    try:
        return (timezone.now() - joined).total_seconds() < minutes * 60
    except Exception:  # noqa: BLE001
        return False


def random_new_email_blocks_card(email: str, user=None) -> bool:
    """Recommend blocking a CARD attempt: a random-looking email on a brand-new
    account. Both halves must agree. Never raises."""
    try:
        if not conf.block_random_new_email():
            return False
        return bool(email) and looks_random_email(email) and account_is_new(user)
    except Exception:  # noqa: BLE001
        logger.exception("random_new_email_blocks_card failed")
        return False
