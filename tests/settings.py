"""The smallest Django that can hold payguard up.

A shared library has to be testable without any of the three products that use
it, or it only ever gets exercised through whichever one someone happened to be
working in -- which is how a library drifts into fitting exactly one caller.

SQLite in memory: payguard owns two small tables and no vendor-specific SQL, so
the tests do not need Postgres to mean anything.
"""
SECRET_KEY = "payguard-tests"
USE_TZ = True
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "payguard",
]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
