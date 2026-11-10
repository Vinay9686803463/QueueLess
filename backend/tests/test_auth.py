import os
from tests.integration_settings import integration_tests_enabled
import uuid

import pytest

from sqlalchemy import text

RUN_INTEGRATION = integration_tests_enabled()
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not RUN_INTEGRATION,
        reason="Set QUEUELESS_RUN_INTEGRATION_TESTS=1 to run Supabase integration tests",
    ),
]


@pytest.fixture()
def registered_user(client, app):
    email = f"queueless-test-{uuid.uuid4()}@example.com"
    password = "TestPassword123!"
    payload = {
        "full_name": "QueueLess Test User",
        "email": email,
        "phone": "9999999999",
        "password": password,
    }

    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 201
    data = response.get_json()
    assert data["status"] == "success"
    assert "password_hash" not in data["user"]

    user_id = data["user"]["id"]
    token = data["access_token"]

    yield {
        "email": email,
        "password": password,
        "user_id": user_id,
        "token": token,
    }

    with app.app_context():
        from app.extensions import db

        db.session.execute(
            text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id},
        )
        db.session.commit()


def test_register_success(client):
    email = f"queueless-test-{uuid.uuid4()}@example.com"
    response = client.post(
        "/api/auth/register",
        json={
            "full_name": "QueueLess Test User",
            "email": email,
            "password": "TestPassword123!",
        },
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["status"] == "success"
    assert data["user"]["email"] == email
    assert "access_token" in data
    assert data["token_type"] == "Bearer"

    with client.application.app_context():
        from app.extensions import db

        db.session.execute(
            text("DELETE FROM users WHERE email = :email"), {"email": email}
        )
        db.session.commit()


def test_register_duplicate_email(client, registered_user):
    response = client.post(
        "/api/auth/register",
        json={
            "full_name": "QueueLess Test User",
            "email": registered_user["email"],
            "password": registered_user["password"],
        },
    )
    assert response.status_code == 409
    assert response.get_json()["status"] == "error"


def test_register_requires_fields(client):
    response = client.post("/api/auth/register", json={"email": "x@example.com"})
    assert response.status_code == 400


def test_login_success(client, registered_user):
    response = client.post(
        "/api/auth/login",
        json={
            "email": registered_user["email"],
            "password": registered_user["password"],
        },
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert "access_token" in data


def test_login_invalid_password(client, registered_user):
    response = client.post(
        "/api/auth/login",
        json={
            "email": registered_user["email"],
            "password": "definitely-wrong",
        },
    )
    assert response.status_code == 401


def test_me_requires_token(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_with_valid_token(client, registered_user):
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["user"]["id"] == registered_user["user_id"]
    assert "password_hash" not in data["user"]
