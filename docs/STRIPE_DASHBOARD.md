# Stripe dashboard checklist (the part payguard can't do)

payguard is the server-side half. These are the dashboard settings **you** apply
once, on the shared Stripe account. They are where a *specific card* gets blocked
(the server never sees card numbers), so they matter.

> The account is **shared** across proxysterr / ipsterr / esimsterr / linksterr /
> coolvpn. These settings are account-wide — they protect all of them at once.

---

## 1. Enable the webhook event payguard learns from

Dashboard → **Developers → Webhooks** → each endpoint → **Add events**:

- ✅ `payment_intent.payment_failed`  ← **required for Layer 7** (the cooldown +
  gold-signal learning). Without it, the failure-driven guards never arm.
- ✅ `charge.dispute.created` (already enabled for dispute alerts — keep it).
- ✅ `checkout.session.completed` (already enabled — this is how top-ups credit).

Do this on **every** endpoint that points at a Sterr backend. Your handler must
return 2xx even for events that aren't yours (it already does — a non-2xx makes
Stripe retry and can disable the endpoint).

## 2. Turn on Radar rules (the card-level blocks)

Dashboard → **Radar → Rules**. Keep the built-in ML risk-score blocks ON, then
add custom rules. Stripe's rule language — adapt thresholds to your volume:

```
# Block obvious card-testing by card fingerprint velocity
Block if :card_velocity_hourly: > 3

# Block when the SAME card was declined repeatedly recently
Block if :card_decline_rate_weekly: > 0.5

# Block high ML risk outright (default reviews ≥ 65; block the worst)
Block if :risk_level: = 'highest'
Review if :risk_level: = 'elevated'

# CVC / postal failures are strong card-testing tells
Block if :cvc_check: = 'fail'
Block if :address_postal_code_check: = 'fail' and :risk_score: > 50

# Same IP hammering many cards
Block if :ip_address: matches velocity (use Radar's IP velocity rule template)
```

Radar → **Lists**: keep a **blocklist** of card fingerprints / emails / IPs you've
confirmed abusive. payguard's `CardAttempt` log is your source for what to add.

## 3. Force 3-D Secure (liability shift + bot wall)

Two places:

- **Server (already set):** the Checkout Session sends
  `payment_method_options.card.request_three_d_secure = "any"`. Keep it.
- **Radar rule (belt & suspenders):**
  ```
  Request 3DS if :risk_level: = 'elevated'
  Request 3DS if :amount: > 10000      # >$100, tune to your ticket sizes
  ```

3DS shifts chargeback liability to the issuer and blocks most card-testing bots,
which can't clear the issuer challenge.

## 4. Raise the bar on new/guest activity

- Radar → **Settings**: enable **"Block if payment is likely fraudulent"** and the
  default card-testing protections (Stripe ships a card-testing rule set — turn it
  on if not already).
- Keep **receipt emails** on (already configured) — real customers expect them;
  bounces flag bad emails.

## 5. Watch the thresholds that cost you money

Dashboard → **Radar → Overview** and **Disputes**:

- Keep the **dispute rate < 0.65%** (Stripe's Dispute program fines start at 0.7%).
- Keep the **fraud rate < 0.75%** (Early Fraud Warnings). Card-testing spikes both.
- Each dispute = a **flat $15 fee** even if you win, plus the amount if you lose —
  this is the real cost the whole system exists to prevent.

## 6. Minimums (already enforced server-side, FYI)

- Card top-ups floor at **$15** (`STRIPE_MIN_TOPUP_USD`) — small card charges bleed
  the fixed $0.30 fee and carry the most chargeback risk, so they're pushed to
  crypto. Keep this.

---

### What's already true in code (don't undo it)

- Credit is granted **only** on the verified webhook (or an authenticated
  success-confirm of the user's own paid session) — never on the frontend result.
- Every top-up endpoint requires an authenticated account (no guest checkout).
- Webhook signatures are verified; unknown/other-product events return 200 and
  are skipped.
