# Payment economics — fees, tax, and where margins thin out

Reference for *why* the payment layer behaves as it does (push to crypto, $15 card
floor, forced 3DS). Numbers are the Sterr proxy ladder as of 2026-10; re-check
when wholesale or retail changes.

## The core mechanic

**The customer is credited the full amount they pay; we absorb the payment fee
and (where owed) the VAT.** Checkout adds no tax line, so today prices behave as
**tax-inclusive** — any VAT obligation comes out of margin, not the customer.
"Net margin" below = profit kept per **$100 the customer pays**.

## Fee layers (we eat these)

| Rail | Effective cost | Notes |
|---|---|---|
| **Crypto** (NowPayments) | ~0.5–1% | no fixed fee → ~99% kept at any size |
| **Card** (Stripe) | ~**4% + $0.30** | ~94% kept at $15, ~96% at $50+. Exact % depends on the Stripe *account country* + card origin (EEA ~1.5%, UK ~2.5%, intl ~3.25% + ~1–2% FX). **Verify the account country.** |
| **Dispute/chargeback** | **$15 flat + lost amount** | even if you win the $15 stands; this is what the fraud layer prevents |

## Tax, country by country (the real risk)

Because nothing is added at checkout, VAT owed = margin lost. Four buckets:

| Customer | Fee | VAT burden | Verdict |
|---|---|---|---|
| Crypto (location opaque) | ~1% | practically uncollected | 🟢 best |
| EU/UK **consumer** card, no VAT ID | ~4% | **EU 17–27% / UK 20%** from us | 🔴 thins deep tiers |
| EU/UK **business** card w/ VAT ID | ~4% | reverse-charge = 0% | 🟢 collect VAT IDs |
| US / rest-of-world card | ~4% | no nexus yet | 🟢 |

Options to stop eating EU/UK VAT: **Stripe Tax** (adds it on top of the deposit)
or route EU/UK cards through **Paddle (Merchant of Record)** — ~5.5% all-in but
Paddle remits all VAT, which beats self-remitting 17–21%. Paddle is already wired
in the backends (gated by API key).

## Net margin — profit kept per $100 paid

| Scenario | Crypto, no VAT | Card, no VAT | Card + EU VAT 21% |
|---|---|---|---|
| Residential entry ($1.79, cost $0.50) | 71% | 68% | 51% |
| Residential deepest ($0.99) | 51% | 48% | 30% |
| Mobile entry ($3.99, cost $2.00) | 49% | 46% | 29% |
| **Mobile deepest ($2.49, cost $1.60)** | 35% | 32% | ⚠️ 14% |
| **Datacenter deepest — current cost $0.45 ($0.59)** | 23% | 20% | 🔴 ~2% (break-even) |
| Datacenter deepest — **Evomi $0.30** | 48% | 45% | 28% |
| **Win-back promo $0.99** (cost $0.50, $15 card min) | 49% | 44% | 26% |

## Takeaways baked into the payment layer

1. **Crypto is ~4–5% cheaper than card** → the $15 card floor + "pay with crypto"
   nudge everywhere is a margin decision, not just UX.
2. **The one danger zone is current-cost datacenter's deepest tier on an EU
   consumer card with VAT owed (~break-even).** Switching datacenter wholesale to
   **Evomi ($0.30)** removes it (and roughly doubles all DC tiers). Highest-ROI
   single change.
3. **Mobile deepest tier + VAT is thin (~14%)** — positive, watch it.
4. **Win-back $0.99 is safe** (~44–49% no-VAT) — it's still ~2× residential cost.
5. **Fraud/chargebacks are a pure margin leak** ($15 + lost amount each) — hence
   payguard + forced 3DS + the <0.65% dispute-rate target.
