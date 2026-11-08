"""Isolated, fast test settings; never use this module for deployment."""

from .settings import *  # noqa: F403

# Test databases remain separate from development and production data.
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
