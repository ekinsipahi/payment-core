# payguard — architecture

The problem: a shared Stripe account was getting hammered by **card-testing**
(bots validating stolen cards with tiny charges). On hosted Checkout the failed
attempts happen on Stripe's page, but each one still costs money/noise, and a
run of them risks Stripe's dispute/fraud thresholds. payguard is the server-side
half of the defense; Stripe Radar + 3DS are the dashboard half.

Each layer below is independent and **fails open** — if its own code or the DB
errors, it allows the request rather than block a paying customer.

---

## Layer 1 — DRF rate throttles (`payguard.throttling`)

Caps how fast *Checkout Session creation* can be called. Three scopes:

| Throttle class | Scope | Keyed on | Default | Applies to |
|---|---|---|---|---|
| `TopupIPThrottle` | `topup_ip` | client IP | 30/hour | all top-ups (crypto + card) |
| `CardTopupIPThrottle` | `card_ip` | client IP | 12/hour | card only |
| `CardTopupUserThrottle` | `card` | account | 8/hour | card only |

Why per-IP matters: the built-in per-account throttle misses the *account-farm*
case — a bot spins up throwaway accounts, all behind one IP. The IP throttle
catches that. Uses the real client IP (left-most `X-Forwarded-For`), because
`REMOTE_ADDR` on Render/Netlify is the internal load balancer.

Throttles **fail open** when the cache is unreachable (DRF behaviour).

## Layer 2 — Disposable-email scoring (`payguard.risk.is_disposable_email`)

Disposable/tempmail domain + card is the classic card-testing profile. We block
~40 known throwaway domains **for card top-ups only**; crypto stays open (no
chargeback to abuse). Extend the list with the `DISPOSABLE_EMAIL_DOMAINS` setting.

## Layer 3 — Exponential multi-key cooldown (`payguard.risk`)

After a **failed** card payment, each identity it touched gets a cooldown that
grows the more it fails:

| fail # | cooldown |
|---|---|
| 1 | free (fat-finger) |
| 2 | 30s |
| 3 | 2 min |
| 4 | 10 min |
| 5+ | 1 hour |

Tracked **per identity dimension** — account, client IP, email, and Stripe card
fingerprint — in `CardCooldown` (one row per `(kind, key)`). A bot that rotates
*one* dimension still trips on the others. A new card session is refused while
**any** of its account/IP/email keys is still blocked (fingerprint is unknown at
session-creation, so it can't gate — it only feeds Layer 7). Counters **decay**
after 24h of quiet so a legit customer isn't punished days later.

## Layer 4 — Open-session velocity guard (`payguard.gates.card_velocity_guard`)

A real customer opens one Checkout and pays it. Stacking several **uncredited**
sessions in a few minutes is the testing fingerprint. The caller counts its own
recent uncredited card `Payment`s and passes the number in; ≥ `CARD_MAX_OPEN_SESSIONS`
(default 3 in `CARD_SESSION_WINDOW_MIN`=10 min) → block. Kept caller-side so
payguard stays decoupled from each product's Payment schema.

## Layer 5 — Forced 3-D Secure (Stripe Checkout param)

`payment_method_options.card.request_three_d_secure = "any"` on the Checkout
Session requests 3DS on **every** card, not just when SCA forces it. Frictionless
3DS passes invisibly for legit cards but blocks most bots (they can't clear the
issuer challenge) and shifts fraud liability to the issuer. This is set when you
create the session (see INTEGRATION.md) — it's not a payguard call, but it's part
of the design and must stay on.

## Layer 6 — Stripe Radar (dashboard)

Radar's ML + your custom rules are the only place that can block a *specific card
/ fingerprint* before the charge, since the card number never reaches you. This
is dashboard config — see [STRIPE_DASHBOARD.md](STRIPE_DASHBOARD.md). payguard
complements Radar; it does not replace it.

## Layer 7 — Learn from failures (`payguard.risk.record_card_failure`)

Fed by the Stripe `payment_intent.payment_failed` webhook. For each failure it:

1. logs a `CardAttempt` row (account, IP, email, fingerprint, time);
2. bumps the Layer-3 ladder on all four keys;
3. runs the **gold signal** — the strongest card-testing tell.

### The gold signal — one account, many different cards

```
account A   09:01 card X declined
            09:02 card Y declined
            09:03 card Z declined   ← 3 distinct fingerprints in minutes
```

No real customer does this. When distinct failed fingerprints for an account in
`CARD_DISTINCT_WINDOW_MIN` (30 min) reach `CARD_DISTINCT_FINGERPRINTS` (3), we
slam a long cooldown on the account **and** its IP: `CARD_MULTICARD_COOLDOWN_MIN`
(30 min) base, **doubling per extra card**, capped at 6 hours.

> Fingerprints come only from Stripe's webhook, so Layer 7 is dormant until you
> enable `payment_intent.payment_failed` in the dashboard (STRIPE_DASHBOARD.md).
> Layers 1–4 work immediately with no dashboard change.

---

## Data model

- **`CardCooldown`** (`payguard_card_cooldowns`) — aggregate cooldown state, one
  row per `(kind, key)`. `kind ∈ {account, ip, email, fingerprint}`.
- **`CardAttempt`** (`payguard_card_attempts`) — append-only failure log; powers
  the distinct-card count and doubles as a dispute audit trail.

Neither stores a card number — only Stripe's safe `fingerprint`.

## Tunables (Django settings / env)

| Setting | Default | Meaning |
|---|---|---|
| `CARD_MAX_OPEN_SESSIONS` | 3 | open uncredited card sessions before block |
| `CARD_SESSION_WINDOW_MIN` | 10 | window for the above |
| `CARD_DISTINCT_FINGERPRINTS` | 3 | distinct cards/account that trip the gold signal |
| `CARD_DISTINCT_WINDOW_MIN` | 30 | window for the gold signal |
| `CARD_MULTICARD_COOLDOWN_MIN` | 30 | base penalty (doubles/card, cap 6h) |
| `DISPOSABLE_EMAIL_DOMAINS` | `[]` | extra domains to block on card |
| throttle rates `topup_ip`/`card`/`card_ip` | 30/8/12 per hour | see Layer 1 |

Set any to a non-positive value to disable that guard.
