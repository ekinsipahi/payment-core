"""The randomness heuristic, judged on who it turns away.

This is the only guard in payguard that refuses a payment on the strength of
what somebody's address *looks like*. Everything else waits for a card to be
declined first. So the test that matters is not "does it catch gibberish" -- it
is "does it catch a customer", and the answer has to be no.
"""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import override_settings

from .base import CacheIsolatedTestCase
from django.utils import timezone

from payguard.email_reputation import (account_is_new, looks_random_email,
                                       random_new_email_blocks_card)

User = get_user_model()

# Real names, written the way the people they belong to write them. Several of
# these were refused before the alphabet was folded: an ASCII-only vowel set
# counts ü, ı, ö and ø as consonants, so a Turkish or Norwegian name reads to it
# as machine-generated while the same name transliterated sails through.
REAL_PEOPLE = [
    "mehmetşükrüyıldırım@gmail.com",      # Turkish, written in Turkish
    "mehmetsukruyildirim@gmail.com",      # the same name, transliterated
    "gülşençiğdemöztürk@gmail.com",
    "krzysztofwszczyzna@gmail.com",       # Polish: y is a vowel there
    "jørgenkristiansen@gmail.com",        # Norwegian
    "vojtěchnovotný@gmail.com",           # Czech
    "maria.gonzalez.ruiz@gmail.com",
    "john.smith.london@gmail.com",
]

MACHINE_MINTED = [
    "x7f9qk2j8d3h1@gmail.com",
    "a1b2c3d4e5f6g7@gmail.com",
    "zxcvbnmqwrtzxcvbn@gmail.com",
    "kjhgfdszxcvbnmlkj@gmail.com",
    "qwrtpsdfghjklzxc@gmail.com",
]


class RandomnessTests(CacheIsolatedTestCase):
    def test_a_name_in_its_own_alphabet_is_not_machine_generated(self):
        for email in REAL_PEOPLE:
            with self.subTest(email=email):
                self.assertFalse(looks_random_email(email),
                                 f"{email} is a person, not a script")

    def test_the_same_name_scores_the_same_in_either_alphabet(self):
        # The one that proves the fold works: if these disagree, the guard is
        # judging the writing system rather than the string.
        self.assertEqual(looks_random_email("mehmetşükrüyıldırım@gmail.com"),
                         looks_random_email("mehmetsukruyildirim@gmail.com"))

    def test_minted_inboxes_are_still_caught(self):
        for email in MACHINE_MINTED:
            with self.subTest(email=email):
                self.assertTrue(looks_random_email(email))

    def test_a_short_address_is_never_judged(self):
        # Too little to go on, and plenty of real addresses are short.
        self.assertFalse(looks_random_email("kz9@gmail.com"))

    def test_nonsense_input_does_not_raise(self):
        for value in ("", "   ", "no-at-sign", "@gmail.com", None):
            with self.subTest(value=value):
                self.assertFalse(looks_random_email(value or ""))


@override_settings(CARD_NEW_ACCOUNT_MIN=15, CARD_BLOCK_RANDOM_NEW_EMAIL=True)
class BothHalvesTests(CacheIsolatedTestCase):
    """Neither signal blocks on its own, which is the whole design."""

    def _user(self, email, age_minutes):
        user = User.objects.create_user(username=email.split("@")[0][:30], email=email)
        User.objects.filter(pk=user.pk).update(
            date_joined=timezone.now() - timedelta(minutes=age_minutes))
        user.refresh_from_db()
        return user

    def test_a_random_address_on_an_established_account_is_left_alone(self):
        user = self._user("x7f9qk2j8d3h1@gmail.com", age_minutes=60 * 24 * 30)
        self.assertFalse(random_new_email_blocks_card(user.email, user))

    def test_a_real_address_on_a_brand_new_account_is_left_alone(self):
        user = self._user("mehmetşükrüyıldırım@gmail.com", age_minutes=1)
        self.assertTrue(account_is_new(user))
        self.assertFalse(random_new_email_blocks_card(user.email, user))

    def test_only_both_together_recommend_a_block(self):
        user = self._user("x7f9qk2j8d3h1@gmail.com", age_minutes=1)
        self.assertTrue(random_new_email_blocks_card(user.email, user))

    def test_an_account_with_no_join_date_is_not_treated_as_new(self):
        self.assertFalse(account_is_new(None))

    @override_settings(CARD_BLOCK_RANDOM_NEW_EMAIL=False)
    def test_the_whole_rule_can_be_switched_off(self):
        user = self._user("x7f9qk2j8d3h1@gmail.com", age_minutes=1)
        self.assertFalse(random_new_email_blocks_card(user.email, user))
