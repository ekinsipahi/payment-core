"""One mailbox must be one identity, however it is spelled.

Counting addresses literally is the cheapest evasion there is: plus-addressing
works everywhere and Gmail ignores dots, so a single inbox can present an
unbounded number of distinct-looking addresses, each arriving with a clean
record. This turned up in esimsterr's live traffic on the first day the app was
public, as `d.a.w.di2153azdin@gmail.com`.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from payguard import card_cooldown_remaining, record_card_failure
from payguard.risk import canonical_email, is_disposable_email

User = get_user_model()


class CanonicalEmailTests(TestCase):
    def test_every_gmail_spelling_collapses_to_one_key(self):
        target = canonical_email("dawdi2153azdin@gmail.com")
        for spelling in (
            "d.a.w.di2153azdin@gmail.com",
            "DAW.DI2153AZDIN@gmail.com",
            "dawdi2153azdin+shop@gmail.com",
            "d.a.w.di.2153azdin@googlemail.com",
        ):
            with self.subTest(spelling=spelling):
                self.assertEqual(canonical_email(spelling), target)

    def test_a_dot_still_separates_two_strangers_elsewhere(self):
        # Only Gmail is dot-blind. Collapsing them everywhere would merge two
        # unrelated Outlook customers and make each serve the other's cooldown.
        self.assertNotEqual(canonical_email("first.last@outlook.com"),
                            canonical_email("firstlast@outlook.com"))

    def test_plus_addressing_is_stripped_everywhere(self):
        # Plus-addressing is a standard every provider honours.
        self.assertEqual(canonical_email("someone+receipts@fastmail.com"),
                         canonical_email("someone@fastmail.com"))

    def test_rubbish_in_does_not_raise(self):
        for value in ("", "   ", "no-at-sign", "@gmail.com"):
            with self.subTest(value=value):
                canonical_email(value)


class CooldownFollowsTheMailboxTests(TestCase):
    def test_a_new_spelling_does_not_buy_a_clean_record(self):
        user = User.objects.create_user(username="a", email="dawdi2153azdin@gmail.com")
        for _ in range(3):
            record_card_failure(user=user, email="d.a.w.di2153azdin@gmail.com")
        # Different account, different spelling, same mailbox.
        self.assertGreater(
            card_cooldown_remaining(email="dawdi2153azdin+again@googlemail.com"), 0)


class DomainsFromTheAccessLogTests(TestCase):
    def test_the_throwaway_providers_seen_on_launch_day_are_known(self):
        for domain in ("moimoi.re", "mailto.plus", "fexpost.com", "rover.info"):
            with self.subTest(domain=domain):
                self.assertTrue(is_disposable_email(f"someone@{domain}"))

    def test_an_ordinary_provider_is_not_swept_up(self):
        for domain in ("gmail.com", "outlook.com", "proton.me", "fastmail.com"):
            with self.subTest(domain=domain):
                self.assertFalse(is_disposable_email(f"someone@{domain}"))
