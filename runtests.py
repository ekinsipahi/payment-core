#!/usr/bin/env python3
"""Run payguard's tests without a host project: `python runtests.py`."""
import os
import sys

import django
from django.conf import settings
from django.test.utils import get_runner

if __name__ == "__main__":
    os.environ["DJANGO_SETTINGS_MODULE"] = "tests.settings"
    django.setup()
    runner = get_runner(settings)(verbosity=1)
    sys.exit(bool(runner.run_tests(["tests"])))
