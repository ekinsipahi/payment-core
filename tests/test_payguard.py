"""What payguard promises, checked without any product around it.

Three backends are about to trust this with their card traffic, so both halves
have to hold: strict enough to stop somebody working through a list of stolen
numbers, and forgiving enough not to turn away a customer whose first card was
declined. Tests that only prove the blocking half will happily ship the other.
"""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import override_settings

from .base import CacheIsolatedTestCase
from django.utils import timezone

from payguard import (CardBlocked, card_cooldown_remaining, card_risk_gate,
                      client_ip, fingerprint_from_failed_pi, is_disposable_email,
                      record_card_failure, remember_checkout_ip)
from payguard.gates import card_velocity_guard
from payguard.models import CardCooldown

User = get_user_model()
IP = "203.0.113.9"


class LadderTests(CacheIsolatedTestCase):
    """First decline free, then 30s / 2m / 10m / 1h."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username="buyer", email="buyer@example.com")

    def fail(self, fingerprint=None):
        record_card_failure(user=self.user, email=self.user.email, fingerprint=fingerprint)

    def wait(self):
        return card_cooldown_remaining(user=self.user, email=self.user.email)

    def test_one_decline_costs_nothing(self):
        # The commonest reason for a single decline is a mistyped digit.
        # Charging for that is a lost sale, not a defence.
        self.fail()
        self.assertEqual(self.wait(), 0)

    def test_the_wait_grows_with_each_further_decline(self):
        seen = []
        for _ in range(5):
            self.fail()
            seen.append(self.wait())
        self.assertEqual(seen[0], 0)
        self.assertEqual(seen, sorted(seen), f"ladder went backwards: {seen}")
        self.assertGreaterEqual(seen[-1], 3600)

    def test_a_quiet_day_forgives_the_count(self):
        # Somebody who failed twice last week is not mid-attack today.
        self.fail(); self.fail()
        old = timezone.now() - timedelta(hours=48)
        CardCooldown.objects.update(last_fail_at=old, blocked_until=old)
        self.assertEqual(self.wait(), 0)


class GoldSignalTests(CacheIsolatedTestCase):
    """Declined, try another card, declined, try another. Nobody owns four
    cards they expect to fail."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username="tester", email="t@example.com")

    def test_several_distinct_cards_earn_a_long_block(self):
        for fp in ("fpA", "fpB", "fpC"):
            record_card_failure(user=self.user, ip=IP, email=self.user.email, fingerprint=fp)
        self.assertGreaterEqual(
            card_cooldown_remaining(user=self.user, email=self.user.email), 30 * 60)

    def test_the_same_card_retried_is_only_the_ladder(self):
        # A bad card is a bad card, not a list. It still costs rungs; it must
        # not cost the half-hour the gold signal hands out.
        for _ in range(3):
            record_card_failure(user=self.user, ip=IP, email=self.user.email, fingerprint="fpA")
        self.assertLess(card_cooldown_remaining(user=self.user, email=self.user.email), 30 * 60)


@override_settings(CARD_IP_COOLDOWN_FACTOR=0.25)
class SharedAddressTests(CacheIsolatedTestCase):
    """An airport is one address and hundreds of customers."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username="traveller", email="trav@example.com")

    def test_an_address_serves_less_than_an_account(self):
        for fp in ("fpA", "fpB", "fpC"):
            record_card_failure(user=self.user, ip=IP, email=self.user.email, fingerprint=fp)
        account = card_cooldown_remaining(user=self.user)
        address = card_cooldown_remaining(ip=IP)
        self.assertGreater(address, 0, "the address should still count for something")
        self.assertLess(address, account, "the address must not serve the full sentence")

    @override_settings(CARD_IP_COOLDOWN_FACTOR=1.0)
    def test_a_product_without_shared_addresses_can_turn_it_off(self):
        for fp in ("fpA", "fpB", "fpC"):
            record_card_failure(user=self.user, ip=IP, email=self.user.email, fingerprint=fp)
        self.assertEqual(card_cooldown_remaining(ip=IP),
                         card_cooldown_remaining(user=self.user))

    def test_a_stranger_behind_the_same_address_can_still_pay(self):
        # One decline from one person must not cost everybody on the NAT.
        record_card_failure(user=self.user, ip=IP, email=self.user.email)
        other = User.objects.create_user(username="other", email="other@example.com")
        card_risk_gate(other, client_ip=IP)


class EmailTests(CacheIsolatedTestCase):
    def test_throwaway_inboxes_are_recognised(self):
        self.assertTrue(is_disposable_email("a@mailinator.com"))
        self.assertFalse(is_disposable_email("a@gmail.com"))

    def test_the_gate_refuses_one_before_anything_has_failed(self):
        user = User.objects.create_user(username="burner", email="x@mailinator.com")
        with self.assertRaises(CardBlocked):
            card_risk_gate(user)

    def test_a_real_address_passes(self):
        user = User.objects.create_user(username="real", email="x@gmail.com")
        card_risk_gate(user)


class VelocityTests(CacheIsolatedTestCase):
    @override_settings(CARD_MAX_OPEN_SESSIONS=3)
    def test_too_many_unfinished_checkouts_is_refused(self):
        card_velocity_guard(2)
        with self.assertRaises(CardBlocked):
            card_velocity_guard(3)

    @override_settings(CARD_MAX_OPEN_SESSIONS=0)
    def test_the_cap_can_be_switched_off(self):
        card_velocity_guard(99)


class FailOpenTests(CacheIsolatedTestCase):
    """A guard that breaks must not take the checkout down with it.

    Every one of these is a real payment being refused for a reason that has
    nothing to do with the customer, which is worse than the abuse it prevents.
    """

    def test_recording_a_failure_with_nothing_to_go_on_does_not_raise(self):
        record_card_failure()

    def test_an_unknown_caller_has_no_cooldown(self):
        self.assertEqual(card_cooldown_remaining(), 0)

    def test_a_gate_with_no_user_and_no_address_lets_the_sale_through(self):
        card_risk_gate(None)


class FingerprintTests(CacheIsolatedTestCase):
    def test_it_is_read_from_the_failed_intent(self):
        pi = {"last_payment_error": {"payment_method": {"card": {"fingerprint": "abc123"}}}}
        self.assertEqual(fingerprint_from_failed_pi(pi), "abc123")

    def test_a_shape_we_did_not_expect_yields_nothing_rather_than_raising(self):
        for pi in ({}, {"last_payment_error": None}, {"last_payment_error": {"payment_method": {}}}):
            self.assertEqual(fingerprint_from_failed_pi(pi), "")


class ClientIpTests(CacheIsolatedTestCase):
    """A backend behind Cloudflare (linksterr) and one directly behind
    Render's edge (proxysterr, esimsterr) must both get the real visitor,
    never the client-forgeable header the OTHER kind of edge would trust."""

    def _req(self, **meta):
        class R:
            META = meta
        return R()

    def test_cloudflare_header_wins_when_present(self):
        # CF overwrites this at the edge; a client cannot forge it. Must win
        # even over a client-supplied XFF trying to claim a different IP.
        req = self._req(HTTP_CF_CONNECTING_IP="203.0.113.9",
                        HTTP_X_FORWARDED_FOR="198.51.100.1, 10.0.0.1",
                        REMOTE_ADDR="10.0.0.1")
        self.assertEqual(client_ip(req), "203.0.113.9")

    def test_falls_back_to_forwarded_for_without_cloudflare(self):
        # proxysterr/esimsterr today: no Cloudflare in front, Render's own
        # edge sets XFF correctly.
        req = self._req(HTTP_X_FORWARDED_FOR="198.51.100.1, 10.0.0.1",
                        REMOTE_ADDR="10.0.0.1")
        self.assertEqual(client_ip(req), "198.51.100.1")

    def test_falls_back_to_remote_addr_as_last_resort(self):
        req = self._req(REMOTE_ADDR="10.0.0.1")
        self.assertEqual(client_ip(req), "10.0.0.1")

    def test_none_request_returns_none(self):
        self.assertIsNone(client_ip(None))


class CheckoutIpMemoryTests(CacheIsolatedTestCase):
    """record_card_failure needs the IP that was live at checkout time, but
    Stripe's payment_intent.payment_failed payload never carries it. proxysterr
    threads it through its own Payment.raw column; a product whose card
    checkout is a bare redirect with no pending-order row (linksterr's
    subscription flow) has nowhere else to put it. card_risk_gate remembers
    (email, client_ip) for exactly this case, and record_card_failure recalls
    it when ip isn't passed explicitly — so a product keeps doing its own
    thing by passing ip=, and one without that plumbing gets it for free."""

    def _user(self, tag):
        # distinct email per test — the checkout-IP memory lives in LocMemCache,
        # outside the DB transaction a TestCase rolls back, so sharing one email
        # across methods would leak a remembered IP from an earlier test.
        return User.objects.create_user(username=tag, email=f"{tag}@example.com")

    def test_gate_remembers_ip_and_failure_recalls_it(self):
        u = self._user("remembers")
        card_risk_gate(u, client_ip=IP, email=u.email)
        record_card_failure(user=u, email=u.email)   # no ip= passed
        self.assertTrue(CardCooldown.objects.filter(
            kind=CardCooldown.Kind.IP, key=IP).exists())

    def test_explicit_ip_overrides_the_remembered_one(self):
        """A product with its own Payment.raw-style tracking is unaffected —
        its explicit ip= is never second-guessed by the cache."""
        u = self._user("explicitwins")
        card_risk_gate(u, client_ip=IP, email=u.email)
        other_ip = "198.51.100.7"
        record_card_failure(user=u, email=u.email, ip=other_ip)
        self.assertTrue(CardCooldown.objects.filter(
            kind=CardCooldown.Kind.IP, key=other_ip).exists())
        self.assertFalse(CardCooldown.objects.filter(
            kind=CardCooldown.Kind.IP, key=IP).exists())

    def test_without_a_prior_gate_call_no_ip_key_is_invented(self):
        """No memory, no explicit ip= → the failure is still logged and
        laddered on account+email alone, nothing IP-shaped appears."""
        u = self._user("noip")
        record_card_failure(user=u, email=u.email)
        self.assertEqual(CardCooldown.objects.filter(kind=CardCooldown.Kind.IP).count(), 0)

    def test_remember_checkout_ip_can_be_called_directly(self):
        """For a product gating some other way than card_risk_gate."""
        remember_checkout_ip("direct@example.com", IP)
        record_card_failure(email="direct@example.com")
        self.assertTrue(CardCooldown.objects.filter(
            kind=CardCooldown.Kind.IP, key=IP).exists())


class SuccessClearsTheLadderTests(CacheIsolatedTestCase):
    """Paying is the strongest possible evidence of not being an attack."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username="payer", email="payer@example.com")

    def test_a_card_that_works_releases_the_cooldown(self):
        from payguard import record_card_success

        for _ in range(3):
            record_card_failure(user=self.user, ip=IP, email=self.user.email)
        self.assertGreater(card_cooldown_remaining(user=self.user, email=self.user.email), 0)
        record_card_success(user=self.user, ip=IP, email=self.user.email)
        self.assertEqual(card_cooldown_remaining(user=self.user, email=self.user.email), 0)

    def test_the_declined_card_itself_is_not_vouched_for(self):
        # One success on a different card says nothing about the one that kept
        # being refused, which may well be somebody else's.
        from payguard import record_card_success

        for _ in range(4):
            record_card_failure(user=self.user, ip=IP, email=self.user.email, fingerprint="fpBad")
        record_card_success(user=self.user, ip=IP, email=self.user.email)
        self.assertTrue(CardCooldown.objects.filter(kind="fingerprint", key="fpBad").exists())

    def test_clearing_with_nothing_to_clear_does_not_raise(self):
        from payguard import record_card_success

        record_card_success()

    def test_success_recalls_the_remembered_ip_too(self):
        """A webhook handler is Stripe calling your server, not a browser
        request — it rarely has the client IP to hand. record_card_success
        should recall it the same way record_card_failure does, so the
        address key clears along with account+email instead of being
        stranded on its cooldown."""
        from payguard import card_risk_gate, record_card_success

        card_risk_gate(self.user, client_ip=IP, email=self.user.email)
        for _ in range(3):
            record_card_failure(user=self.user, email=self.user.email)   # ip recalled, same as success will do
        self.assertTrue(CardCooldown.objects.filter(kind="ip", key=IP).exists())
        record_card_success(user=self.user, email=self.user.email)       # no ip= passed
        self.assertFalse(CardCooldown.objects.filter(kind="ip", key=IP).exists())
