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

## Layer 2 — Email reputation (`payguard.risk` + `payguard.email_reputation`)

Two card-only pre-checks (crypto always stays open — no chargeback to abuse):

- **Disposable / tempmail domain** (`is_disposable_email`) → block. A throwaway
  domain + card is the classic card-testing profile. ~40 built-in domains;
  extend with the `DISPOSABLE_EMAIL_DOMAINS` setting.
- **Random-looking email on a brand-new account** (`random_new_email_blocks_card`)
  → deflect to crypto. `x7f9qk2j8@…` minted minutes ago is a bot tell. Because
  legit users sometimes have alias-style addresses, this fires only when **both**
  signals agree (random-looking local part **and** account younger than
  `CARD_NEW_ACCOUNT_MIN`). After that window the same account's card works
  normally. Set `CARD_BLOCK_RANDOM_NEW_EMAIL=False` to score without blocking.

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

## Shared addresses, and why an IP is not a person

Every cooldown above applies to the account, the IP and the email alike. For an
IP that is wrong here, and wrong in a way that costs customers rather than
catching anybody.

Many products serve people behind shared addresses *by design*. Travellers sit
behind one NAT address at an airport, a hotel or on a cruise ship; mobile
carriers put thousands of subscribers behind one CGNAT address; some products
resell the shared exit address itself. A six-hour block on one of those — which
is what the gold signal hands out — does not inconvenience an attacker, who
changes address in seconds; it locks out every paying customer sitting behind
it, and they do not complain, they leave.

So an IP serves `CARD_IP_COOLDOWN_FACTOR` of whatever an account would serve,
0.25 by default. The address still counts: one machine grinding through a list
from one place still slows down, which is the case per-IP limits are actually
good for. What it no longer does is turn a crowded airport into a blocked
address because one person on it had a bad card.

The rules that catch a distributed attempt are the account ladder and the
distinct-card signal, and neither of them cares what address it arrived from.
That is the point — the IP was never the load-bearing key, so weakening it
costs little and removing a false positive from a travel product is worth a
great deal.

Applied inside `_force_block`, so every route to an address block is softened
identically and a new one cannot be added that forgets to. Set it to `1.0` for a
product whose customers each have their own address.

## Tunables (Django settings / env)

| Setting | Default | Meaning |
|---|---|---|
| `CARD_MAX_OPEN_SESSIONS` | 3 | open uncredited card sessions before block |
| `CARD_SESSION_WINDOW_MIN` | 10 | window for the above |
| `CARD_DISTINCT_FINGERPRINTS` | 3 | distinct cards/account that trip the gold signal |
| `CARD_DISTINCT_WINDOW_MIN` | 30 | window for the gold signal |
| `CARD_MULTICARD_COOLDOWN_MIN` | 30 | base penalty (doubles/card, cap 6h) |
| `CARD_IP_COOLDOWN_FACTOR` | 0.25 | fraction of a cooldown an **IP** serves (see below) |
| `DISPOSABLE_EMAIL_DOMAINS` | `[]` | extra domains to block on card |
| `CARD_BLOCK_RANDOM_NEW_EMAIL` | `True` | block random-looking email on a brand-new account |
| `CARD_NEW_ACCOUNT_MIN` | 60 | "brand-new" account window, minutes (0 disables the age half) |
| `CARD_RANDOM_EMAIL_MIN_LEN` | 10 | min local-part length before the randomness test applies |
| `CARD_RANDOM_EMAIL_DIGIT_RATIO` | 0.35 | digit ratio that marks a local part random |
| throttle rates `topup_ip`/`card`/`card_ip` | 30/8/12 per hour | see Layer 1 |

Set any to a non-positive value to disable that guard.
