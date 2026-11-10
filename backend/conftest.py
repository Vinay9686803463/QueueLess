import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

# Integration tests must never silently use the production database.
if os.getenv("QUEUELESS_RUN_INTEGRATION_TESTS") == "1":
    from tests.integration_settings import assert_safe_test_database

    assert_safe_test_database()
    os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", "").strip()

from app import create_app
from app.utils.rate_limit import rate_limiter


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: tests that use a separate test database"
    )


@pytest.fixture(scope="session")
def app():
    return create_app()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Prevent in-memory rate-limit state from leaking between tests."""
    rate_limiter.reset()
    yield
    rate_limiter.reset()
