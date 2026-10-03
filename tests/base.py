"""A TestCase that starts with an empty cache.

Django's TestCase wraps each test in a transaction and rolls the database back,
but it does not touch the cache — and payguard keeps real state there: the
checkout-IP memory that `card_risk_gate` writes and `record_card_failure` reads.

Left alone, one test's remembered address survives into the next and the suite
starts depending on the order it happens to run in. That showed up exactly as
you would expect it to: a test asserting "no IP key was invented" passed on its
own, failed in the full suite, and passed again under a debugger. A suite that
answers differently depending on what ran before it is worse than no suite,
because it teaches you to ignore it.
"""
from django.core.cache import cache
from django.test import TestCase


class CacheIsolatedTestCase(TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
