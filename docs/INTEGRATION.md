# Integrating payguard into a backend

This mirrors exactly what landed in **proxysterr**; esimsterr and linksterr apply
the same steps. payguard touches only the card path — crypto is left alone.

## 0. Install + migrate

```python
# config/settings.py
INSTALLED_APPS += ["payguard"]
```
```bash
python manage.py migrate payguard      # creates payguard_card_cooldowns + _card_attempts
```

> Render does **not** auto-migrate on deploy. Apply this migration to prod
> yourself (venv migrate against the pooler) or via a Pre-Deploy Command, and do
> it *with* the deploy — payguard's code paths reference the new tables.

## 1. Settings — throttle rates + knobs

```python
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].update({
    "topup_ip": env("THROTTLE_TOPUP_IP", default="30/hour"),  # all top-ups, per IP
    "card":     env("THROTTLE_CARD",     default="8/hour"),   # card, per account
    "card_ip":  env("THROTTLE_CARD_IP",  default="12/hour"),  # card, per IP
})

# Guard knobs (all optional; these are the defaults)
CARD_MAX_OPEN_SESSIONS      = env.int("CARD_MAX_OPEN_SESSIONS", default=3)
CARD_SESSION_WINDOW_MIN     = env.int("CARD_SESSION_WINDOW_MIN", default=10)
CARD_DISTINCT_FINGERPRINTS  = env.int("CARD_DISTINCT_FINGERPRINTS", default=3)
CARD_DISTINCT_WINDOW_MIN    = env.int("CARD_DISTINCT_WINDOW_MIN", default=30)
CARD_MULTICARD_COOLDOWN_MIN = env.int("CARD_MULTICARD_COOLDOWN_MIN", default=30)
DISPOSABLE_EMAIL_DOMAINS    = env.list("DISPOSABLE_EMAIL_DOMAINS", default=[])
```

A shared cache (Redis/Memcached) is recommended so throttles work across workers;
with LocMemCache each process throttles independently (still fine as a floor).

## 2. Views — throttles on the top-up endpoints

```python
from payguard.throttling import (
    CardTopupIPThrottle, CardTopupUserThrottle, TopupIPThrottle,
)
from payguard import client_ip

class CreateTopupView(APIView):           # crypto
    throttle_classes = [ScopedRateThrottle, TopupIPThrottle]
    throttle_scope = "payment"

class CreateStripeTopupView(APIView):     # card
    throttle_classes = [CardTopupUserThrottle, CardTopupIPThrottle, TopupIPThrottle]
    def post(self, request):
        ...
        data = services.create_stripe_topup(
            request.user, amount, origin=origin or None,
            client_ip=client_ip(request),           # <-- pass real IP
        )
```

(`CreatePaddleTopupView` gets the same card throttles + `client_ip`.)

## 3. Service — gate before creating the session

```python
from payguard import card_risk_gate
from payguard.gates import card_velocity_guard

def create_stripe_topup(user, amount_usd, *, origin=None, client_ip=None):
    if not settings.STRIPE_SECRET_KEY:
        raise ValueError("Card payments aren't available yet — pay with crypto.")
    card_risk_gate(user, client_ip=client_ip)          # disposable + cooldown

    # velocity: count YOUR own recent uncredited card sessions, pass the number
    from datetime import timedelta
    from django.utils import timezone
    since = timezone.now() - timedelta(minutes=settings.CARD_SESSION_WINDOW_MIN)
    open_n = Payment.objects.filter(
        user=user, provider=Payment.Provider.STRIPE,
        credited=False, created_at__gte=since,
    ).count()
    card_velocity_guard(open_n)

    ... create Order + Payment + Stripe session ...
    # stash the IP so the failure webhook can attribute to it:
    payment.raw = {"session_id": session.get("id", ""), "client_ip": client_ip or ""}
```

`card_risk_gate` / `card_velocity_guard` raise `payguard.CardBlocked`
(a `ValueError`), so your existing `except ValueError → 400` already returns a
clean, customer-safe message.

## 4. Checkout session — force 3DS

```python
params["payment_method_options"] = {"card": {"request_three_d_secure": "any"}}
params["payment_intent_data"] = {"metadata": {"payment_id": payment_id}}  # needed in step 5
```

## 5. Webhook — learn from failures

```python
from payguard import fingerprint_from_failed_pi, is_uuid, sf, record_card_failure

def process_stripe_webhook(event):
    etype = sf(event, "type", default="")
    if etype == "payment_intent.payment_failed":
        pi = sf(event, "data", "object")
        ref = sf(pi, "metadata", "payment_id") or ""
        if not is_uuid(ref):
            return                          # not ours (shared account)
        payment = Payment.objects.filter(id=ref).select_related("user").first()
        if not payment:
            return
        raw = payment.raw if isinstance(payment.raw, dict) else {}
        record_card_failure(
            user=payment.user,
            ip=raw.get("client_ip") or None,
            email=getattr(payment.user, "email", "") or None,
            fingerprint=fingerprint_from_failed_pi(pi) or None,
        )
        return
    # ... existing dispute + checkout.session.completed branches ...
```

`record_card_failure` never raises — a guard error can't 500 your webhook.

## 6. Dashboard

Do [STRIPE_DASHBOARD.md](STRIPE_DASHBOARD.md) — at minimum, enable the
`payment_intent.payment_failed` event, or Layer 7 stays dormant.

---

## Rollback / disable

Every guard is individually switchable via settings (set its knob to 0 or its
throttle rate very high). To remove entirely: drop the throttle classes, the
`card_risk_gate`/`card_velocity_guard` calls and the webhook branch; the two
tables can stay (harmless) or be dropped with a reverse migration.
