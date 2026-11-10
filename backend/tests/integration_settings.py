"""Shared settings for optional QueueLess integration tests."""

import os
from urllib.parse import urlparse


def _normalize_database_url(url):
    url = url.strip()

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    return url


def database_identity(url):
    """Return a non-secret identity tuple for a database URL."""
    parsed = urlparse(_normalize_database_url(url))

    return (
        parsed.hostname,
        parsed.port or 5432,
        parsed.path.lstrip("/"),
        parsed.username,
    )


def integration_tests_enabled():
    """Integration tests run only when explicitly enabled and configured."""
    return (
        os.getenv("QUEUELESS_RUN_INTEGRATION_TESTS") == "1"
        and bool(os.getenv("TEST_DATABASE_URL", "").strip())
    )


def assert_safe_test_database():
    """Raise if the configured test database is missing or identical to production."""
    production_url = os.getenv("DATABASE_URL", "").strip()
    test_url = os.getenv("TEST_DATABASE_URL", "").strip()

    if not test_url:
        raise RuntimeError(
            "TEST_DATABASE_URL is required for integration tests. "
            "Refusing to run integration tests without a separate test database."
        )

    if production_url and database_identity(production_url) == database_identity(test_url):
        raise RuntimeError(
            "TEST_DATABASE_URL must not point to the production database."
        )
