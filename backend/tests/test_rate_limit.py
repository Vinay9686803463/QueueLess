import pytest
import time

from flask import Flask, jsonify

from app.utils.rate_limit import RateLimiter


def test_rate_limiter_returns_429_after_limit():
    app = Flask(__name__)
    limiter = RateLimiter()

    @limiter.limit(2, 60)
    def endpoint():
        return jsonify({"status": "success", "message": "ok"}), 200

    with app.test_request_context("/", environ_base={"REMOTE_ADDR": "127.0.0.1"}):
        first = endpoint()
        second = endpoint()
        third = endpoint()

    assert first[1] == 200
    assert second[1] == 200
    assert third[1] == 429
    assert third[0].get_json() == {
        "status": "error",
        "message": "Too many requests. Please try again later.",
    }


def test_rate_limiter_does_not_expose_ip_or_sensitive_data():
    app = Flask(__name__)
    limiter = RateLimiter()

    @limiter.limit(1, 60)
    def endpoint():
        return jsonify({"status": "success", "message": "ok"}), 200

    with app.test_request_context("/", environ_base={"REMOTE_ADDR": "127.0.0.1"}):
        limiter_result = endpoint()
        limited = endpoint()

    assert limited[1] == 429
    body = limited[0].get_json()
    assert "127.0.0.1" not in str(body)
    assert "REMOTE_ADDR" not in str(body)
    assert set(body.keys()) == {"status", "message"}


def test_rate_limited_endpoint_registration():
    from app import create_app

    app = create_app()
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/api/auth/register" in rules
    assert "/api/auth/login" in rules
    assert "/api/public/walk-in" in rules
    assert "/api/public/bookings" in rules

shared_limiter = RateLimiter()


@shared_limiter.limit(1, 60)
def shared_limited_endpoint():
    return jsonify({"status": "success", "message": "ok"}), 200


@pytest.fixture(autouse=True)
def reset_shared_limiter():
    shared_limiter.reset()
    yield
    shared_limiter.reset()


def test_rate_limit_state_is_exhausted_within_one_test():
    with app_test_request_context():
        assert shared_limited_endpoint()[1] == 200
        assert shared_limited_endpoint()[1] == 429


def test_rate_limit_state_does_not_leak_into_next_test():
    with app_test_request_context():
        assert shared_limited_endpoint()[1] == 200


def app_test_request_context():
    from flask import Flask

    app = Flask(__name__)
    return app.test_request_context("/", environ_base={"REMOTE_ADDR": "192.0.2.10"})
