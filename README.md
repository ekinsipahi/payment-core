# payguard — free Stripe card-testing defense & Radar-fee saver

**A free, open card-payment fraud pre-check for Django + Stripe.** Cut
**Stripe Radar fees**, stop **card testing**, and reduce **chargeback / dispute
fees** — without paying for Radar for Fraud Teams.

> **What people search for (and what this is):** *stripe radar fee elimination ·
> no radar fee stripe · cheap stripe radar alternative · reduce stripe radar
> fees · free stripe card testing protection · stop stripe card testing · lower
> stripe chargeback fees · stripe fraud prevention open source · django stripe
> fraud guard.* payguard doesn't remove Stripe's base pricing — it **filters the
> junk card-testing traffic before it reaches Stripe**, so you lean on the free
> standard Radar rules instead of the paid $0.07/decision tier, and you pay far
> fewer $15 dispute fees.

Drop it in front of your Stripe (or Paddle) card top-ups and it blocks
**card-testing / stolen-card** abuse *before* the charge — the failed-attempt
spam that quietly runs up fees and trips Stripe's fraud thresholds. payguard is
**product-agnostic**: it never touches your wallet / credit / order logic. It
answers one question — *"should this card attempt be allowed, and what do we
learn from its failures?"*

MIT-licensed. Use it, fork it, send PRs.

---

## The problem

On **hosted Stripe Checkout** the card form lives on Stripe's page, so a bot
can't brute-force cards against *your* server — but it can:

- spam **Checkout Session creation** from throwaway accounts, and
- grind a list of **stolen cards** on Stripe's page (card-testing),

and every failed attempt still costs you: Stripe/Radar noise, a worse fraud
score, and — once it tips over — **disputes at a flat $15 each** plus the Radar
Fraud-program fines if your rate crosses ~0.7%. The failed attempts you never
"sold" anything on are pure cost. That's the fee bleed payguard exists to stop.

## The approach

Card-testing has a shape a real customer doesn't: many attempts, fast, from
throwaway identities, often many *different* cards on one account. You can't see
the card number (Stripe hosts it), so the plan is:

1. **Slow down** session creation (rate-limit by IP + account + card scope).
2. **Pre-screen** the attempt (disposable / random-new email).
3. **Remember** failures and make repeat attempts wait, escalating.
4. **Catch the signature move** — one account, several different cards in
   minutes — and shut that account down hard.
5. Let **Stripe Radar + 3-D Secure** do the card-level blocking that only they
   can (they see the card; you don't).
6. Never punish the paying customers hiding in the same **shared IP** (airport /
   hotel / mobile CGNAT), and always leave **crypto** open as a clean escape.

## What payguard does (we apply all of these)

- ✅ **Rate throttles** — per client-IP + per-account + per-card scope on top-up
  creation (catches the account-farm-behind-one-IP case the built-ins miss).
- ✅ **Disposable-email block** on card (crypto stays open).
- ✅ **Random-looking email on a brand-new account** → deflect to crypto.
- ✅ **Exponential cooldown after a failed card payment** — 30s → 2m → 10m → 1h,
  tracked across **account + IP + email + card fingerprint**.
- ✅ **Open-session velocity guard** — too many uncredited sessions stacked up.
- ✅ **The gold signal** — one account, several *distinct* card fingerprints in
  minutes → long account cooldown (30 min, doubling per card, cap 6 h).
- ✅ **Shared-IP safety** — an IP serves only a *fraction* of a cooldown, so a
  crowded airport isn't locked out by one bad card.
- ✅ **Learns from Stripe** `payment_intent.payment_failed` (fingerprints, safely
  — never a card number).
- ✅ **Forced 3-D Secure** + a **Stripe Radar rule set** you enable (documented).
- ✅ **Fails open** everywhere — a DB/cache hiccup never blocks a real customer.

## One picture

```
  Card top-up request
        │
   [1] DRF throttles        per-IP + per-account + per-card-IP rate caps
   [2] Email pre-check      disposable / random-new → deflect to crypto
   [3] Cooldown gate        account/IP/email still serving a failed-attempt
   [4] Velocity guard       too many UNCREDITED card sessions open?
        │
        ▼
  Stripe Checkout (hosted) ─► [5] forced 3-D Secure  + [6] Stripe Radar (dashboard)
        │
        ▼
  Webhook: payment_intent.payment_failed
   [7] record_card_failure  learn: bump account+IP+email+fingerprint ladders,
                            and if one account burned several DISTINCT cards in
                            minutes → long account cooldown ("gold signal")
```

Layers 1–4 and 7 are server-side (this package). Layers 5–6 are Stripe
**dashboard** config — see [docs/STRIPE_DASHBOARD.md](docs/STRIPE_DASHBOARD.md).

## Install

```bash
pip install -e .            # or add as a git dependency
```
```python
INSTALLED_APPS += ["payguard"]
```
```bash
python manage.py migrate payguard
```

Then wire the gates, throttles and the webhook branch — copy-paste in
[docs/INTEGRATION.md](docs/INTEGRATION.md).

## Public API

```python
from payguard import (
    is_disposable_email, looks_random_email, card_cooldown_remaining,
    record_card_failure, card_wait_message, card_risk_gate, card_velocity_guard,
    fingerprint_from_failed_pi, client_ip, CardBlocked,
)
```

`card_risk_gate(...)` and `card_velocity_guard(...)` raise `CardBlocked`
(a `ValueError` subclass) with a customer-safe message — so a view that already
maps `ValueError → HTTP 400` keeps working with no change.

## Tests

```bash
python runtests.py
```

No host project required: `tests/settings.py` is the smallest Django that can
hold payguard up, on SQLite in memory.

## Docs

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — every layer, why it exists, the tunables.
- [docs/STRIPE_DASHBOARD.md](docs/STRIPE_DASHBOARD.md) — the Radar rules + events you enable.
- [docs/INTEGRATION.md](docs/INTEGRATION.md) — wire it into a backend (settings, views, webhook).

## Design rules

- **Fail open.** Every guard swallows its own errors — a DB/cache hiccup never
  blocks a real paying customer.
- **Never leak which signal tripped.** Block messages are generic ("too many
  failed attempts, wait / use crypto"), never "your IP is blocked".
- **Crypto is never gated.** There's no chargeback on crypto, so the whole layer
  targets cards; the error always offers crypto as the escape hatch.
- **Store fingerprints, never card numbers.** Only Stripe's safe `fingerprint`.

## License

MIT — see [LICENSE](LICENSE).
