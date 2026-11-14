import importlib.util
from pathlib import Path

import pytest

from tests.integration_settings import (
    assert_safe_test_database,
    integration_tests_enabled,
)


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.py"


def load_config_with_environment(monkeypatch, **environment):
    for name in ("DATABASE_URL", "FLASK_ENV", "SECRET_KEY", "JWT_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)

    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    spec = importlib.util.spec_from_file_location(
        "queueless_config_under_test", CONFIG_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shell_database_url_takes_precedence_over_dotenv(monkeypatch):
    config = load_config_with_environment(
        monkeypatch,
        FLASK_ENV="development",
        DATABASE_URL=(
            "postgresql://queueless_dev_user@127.0.0.1:5432/"
            "queueless_dev?sslmode=disable"
        ),
        SECRET_KEY="test-secret",
    )

    assert config.Config.SQLALCHEMY_DATABASE_URI == (
        "postgresql+psycopg2://queueless_dev_user@127.0.0.1:5432/"
        "queueless_dev?sslmode=disable"
    )


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]"])
def test_production_rejects_loopback_database_hosts(monkeypatch, host):
    with pytest.raises(RuntimeError, match="loopback host"):
        load_config_with_environment(
            monkeypatch,
            FLASK_ENV="production",
            DATABASE_URL=f"postgresql://user@{host}:5432/queueless_dev",
            SECRET_KEY="s" * 32,
            JWT_SECRET_KEY="j" * 32,
        )


def test_integration_database_must_differ_from_primary(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://user@localhost:5432/queueless_dev"
    )
    monkeypatch.setenv(
        "TEST_DATABASE_URL", "postgresql://user@localhost:5432/queueless_test"
    )

    assert_safe_test_database()

    monkeypatch.setenv(
        "TEST_DATABASE_URL", "postgresql://user@localhost:5432/queueless_dev"
    )
    with pytest.raises(RuntimeError, match="must not point to the production database"):
        assert_safe_test_database()


def test_integration_test_database_selection_remains_explicit(monkeypatch):
    monkeypatch.setenv(
        "TEST_DATABASE_URL", "postgresql://user@localhost/queueless_test"
    )
    monkeypatch.delenv("QUEUELESS_RUN_INTEGRATION_TESTS", raising=False)
    assert not integration_tests_enabled()

    monkeypatch.setenv("QUEUELESS_RUN_INTEGRATION_TESTS", "1")
    assert integration_tests_enabled()
