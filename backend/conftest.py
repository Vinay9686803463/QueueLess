import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from sqlalchemy.engine import URL

load_dotenv(ROOT / ".env")

# Integration tests must use only the dedicated local test database.
if os.getenv("QUEUELESS_RUN_INTEGRATION_TESTS") == "1":
    from tests.integration_settings import assert_safe_test_database

    assert_safe_test_database()

    raw_url = os.getenv("TEST_DATABASE_URL", "").strip()
    if not raw_url:
        raise RuntimeError("TEST_DATABASE_URL is required")

    parsed = urlsplit(raw_url)
    credentials, separator, host_port = parsed.netloc.rpartition("@")

    if not separator:
        raise RuntimeError("Invalid TEST_DATABASE_URL")

    username, colon, password = credentials.partition(":")
    if not colon:
        raise RuntimeError("Invalid TEST_DATABASE_URL credentials")

    if ":" in host_port:
        host, port_text = host_port.rsplit(":", 1)
        port = int(port_text)
    else:
        host = host_port
        port = 5432

    database = parsed.path.lstrip("/")

    if host not in ("127.0.0.1", "localhost", "::1"):
        raise RuntimeError("Integration tests blocked: database host must be local")

    if database != "queueless_test":
        raise RuntimeError("Integration tests blocked: only queueless_test is permitted")

    safe_url = URL.create(
        "postgresql+psycopg2",
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
        query=dict(parse_qsl(parsed.query)),
    )

    os.environ["DATABASE_URL"] = safe_url.render_as_string(
        hide_password=False
    )

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
