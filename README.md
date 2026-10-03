# payguard

Shared **card-payment fraud defense** for the Sterr backends (proxysterr,
esimsterr, linksterr). A drop-in Django app that hardens Stripe (and Paddle)
card top-ups against **card-testing / stolen-card** abuse — the thing that was
burning money in Stripe fees on failed attempts.

It was extracted from proxysterr so all three products run the **same** layer
instead of re-implementing it (and drifting) three times. payguard is
**product-agnostic**: it never touches your wallet / credit / order logic. It
only answers one question — *"should this card attempt be allowed, and what do we
learn from its failures?"*

---

## The defense, in one picture

```
  Card top-up request
        │
        ▼
  [1] DRF throttles        per-IP + per-account + per-card-IP rate caps
        │
  [2] Disposable-email     block throwaway domains on CARD (crypto stays open)
        │
  [3] Cooldown gate        account/IP/email still serving a failed-attempt
        │                  cooldown?  (30s → 2m → 10m → 1h, exponential)
        │
  [4] Velocity guard       too many UNCREDITED card sessions open right now?
        │
        ▼
  Stripe Checkout (hosted) ──► [5] forced 3-D Secure  + [6] Stripe Radar  (dashboard)
        │
        ▼
  Webhook: payment_intent.payment_failed
        │
  [7] record_card_failure  learn: bump account+IP+email+fingerprint ladders,
                           and if one account burned several DISTINCT cards in
                           minutes → long account cooldown ("gold signal")
```

Layers 1–4 and 7 live here (server side). Layers 5–6 are Stripe **dashboard**
config — payguard can't set them for you; see [docs/STRIPE_DASHBOARD.md](docs/STRIPE_DASHBOARD.md).

> **Key point about hosted Checkout:** the card form is on Stripe's page, so a
> bot can't brute-force cards against *your* server — only spam *Checkout Session
> creation*. payguard throttles and gates session creation, and learns from the
> failures Stripe reports. Blocking a *specific card* pre-emptively is Radar's
> job (dashboard), because you never see the card number.

---

## Install

```bash
pip install -e /mnt/d/projects/payment-core      # or add as a git/submodule dep
```

```python
# settings.py
INSTALLED_APPS += ["payguard"]
```

```bash
python manage.py migrate payguard
```

Then wire the gates, throttles and webhook branch — full copy-paste in
[docs/INTEGRATION.md](docs/INTEGRATION.md).

## Public API

```python
from payguard import (
    is_disposable_email, card_cooldown_remaining, record_card_failure,
    card_wait_message, card_risk_gate, card_velocity_guard,
    fingerprint_from_failed_pi, client_ip, CardBlocked,
)
```

`card_risk_gate(...)` and `card_velocity_guard(...)` raise `CardBlocked`
(a `ValueError` subclass) with a customer-safe message — so a view that already
maps `ValueError → HTTP 400` keeps working with no change.

## Docs

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — every layer, why it exists, the tunables.
- [docs/STRIPE_DASHBOARD.md](docs/STRIPE_DASHBOARD.md) — the Radar rules + events **you** enable.
- [docs/INTEGRATION.md](docs/INTEGRATION.md) — wire it into a backend (settings, views, webhook).
- [docs/MARGINS.md](docs/MARGINS.md) — fee/tax margin analysis (why card ≠ crypto, where margins thin out).

## Tests

```bash
python runtests.py
```

No host project required: `tests/settings.py` is the smallest Django that can
hold payguard up, on SQLite in memory. A shared library that can only be
exercised through whichever backend somebody happens to be working in is a
library that quietly grows to fit exactly one caller.

## Design rules

- **Fail open.** Every guard swallows its own errors — a DB/cache hiccup never
  blocks a real paying customer.
- **Never leak which signal tripped.** Block messages are generic ("too many
  failed attempts, wait / use crypto"), never "your IP is blocked".
- **Crypto is never gated.** There's no chargeback on crypto, so the whole layer
  targets cards; the error always offers crypto as the escape hatch.
- **Store fingerprints, never card numbers.** Only Stripe's safe `fingerprint`.
