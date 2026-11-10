import os
import uuid

import pytest

from sqlalchemy import text

RUN_INTEGRATION = os.getenv("QUEUELESS_RUN_INTEGRATION_TESTS") == "1"
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
    response = client.post(
        "/api/auth/register",
        json={
            "full_name": "QueueLess Test User",
            "email": email,
            "phone": "9999999999",
            "password": password,
        },
    )
    assert response.status_code == 201
    data = response.get_json()
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


@pytest.fixture()
def owned_business(client, app, registered_user):
    business_name = f"QueueLess Test Business {uuid.uuid4()}"
    response = client.post(
        "/api/businesses",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
        json={
            "business_name": business_name,
            "business_type": "Salon",
            "description": "Test business",
            "address": "Test address",
            "phone": "1234567890",
            "email": "biz@example.com",
            "opening_time": "09:00",
            "closing_time": "18:00",
            "average_service_time": 20,
        },
    )
    assert response.status_code == 201
    data = response.get_json()
    business_id = data["business"]["id"]

    yield registered_user, business_id, business_name

    with app.app_context():
        from app.extensions import db

        db.session.execute(
            text(
                "DELETE FROM businesses WHERE id = :business_id "
                "AND owner_id = :owner_id"
            ),
            {
                "business_id": business_id,
                "owner_id": registered_user["user_id"],
            },
        )
        db.session.commit()


def test_create_business_success(client, registered_user):
    business_name = f"QueueLess Test Business {uuid.uuid4()}"
    response = client.post(
        "/api/businesses",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
        json={
            "business_name": business_name,
            "business_type": "Salon",
            "average_service_time": 15,
        },
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["status"] == "success"
    business = data["business"]
    assert business["business_name"] == business_name
    assert business["owner_id"] == registered_user["user_id"]
    assert business["average_service_time"] == 15

    with client.application.app_context():
        from app.extensions import db

        db.session.execute(
            text(
                "DELETE FROM businesses WHERE id = :business_id "
                "AND owner_id = :owner_id"
            ),
            {
                "business_id": business["id"],
                "owner_id": registered_user["user_id"],
            },
        )
        db.session.commit()


def test_create_business_requires_fields(client, registered_user):
    response = client.post(
        "/api/businesses",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
        json={"business_type": "Salon"},
    )
    assert response.status_code == 400


def test_create_business_requires_auth(client):
    response = client.post(
        "/api/businesses",
        json={"business_name": "No Auth", "business_type": "Salon"},
    )
    assert response.status_code == 401


def test_list_owned_businesses(client, owned_business):
    registered_user, business_id, _ = owned_business
    response = client.get(
        "/api/businesses",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert any(item["id"] == business_id for item in data["businesses"])


def test_get_owned_business(client, owned_business):
    registered_user, business_id, _ = owned_business
    response = client.get(
        f"/api/businesses/{business_id}",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["business"]["id"] == business_id
    assert data["business"]["owner_id"] == registered_user["user_id"]


def test_get_unknown_business_returns_404(client, registered_user):
    response = client.get(
        "/api/businesses/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
    )
    assert response.status_code == 404


def test_update_owned_business(client, owned_business):
    registered_user, business_id, original_name = owned_business
    response = client.put(
        f"/api/businesses/{business_id}",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
        json={
            "business_name": original_name + " Updated",
            "average_service_time": 25,
            "email": "newbiz@example.com",
        },
    )
    assert response.status_code == 200
    data = response.get_json()
    business = data["business"]
    assert business["business_name"].endswith("Updated")
    assert business["average_service_time"] == 25
    assert business["email"] == "newbiz@example.com"


def test_update_rejects_invalid_values(client, owned_business):
    registered_user, business_id, _ = owned_business
    response = client.put(
        f"/api/businesses/{business_id}",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
        json={"average_service_time": 0},
    )
    assert response.status_code == 400


def test_update_requires_payload(client, owned_business):
    registered_user, business_id, _ = owned_business
    response = client.put(
        f"/api/businesses/{business_id}",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
        json={},
    )
    assert response.status_code == 400


def test_unauthorized_business_access(client, app):
    # Create two isolated users and a business owned by the first.
    first_email = f"queueless-test-{uuid.uuid4()}@example.com"
    second_email = f"queueless-test-{uuid.uuid4()}@example.com"
    password = "TestPassword123!"

    first_register = client.post(
        "/api/auth/register",
        json={
            "full_name": "First Test User",
            "email": first_email,
            "password": password,
        },
    )
    second_register = client.post(
        "/api/auth/register",
        json={
            "full_name": "Second Test User",
            "email": second_email,
            "password": password,
        },
    )
    assert first_register.status_code == 201
    assert second_register.status_code == 201

    first = first_register.get_json()
    second = second_register.get_json()
    first_user_id = first["user"]["id"]
    second_token = second["access_token"]

    create_response = client.post(
        "/api/businesses",
        headers={"Authorization": f"Bearer {first['access_token']}"},
        json={"business_name": "Private Business", "business_type": "Salon"},
    )
    assert create_response.status_code == 201
    business_id = create_response.get_json()["business"]["id"]

    try:
        response = client.get(
            f"/api/businesses/{business_id}",
            headers={"Authorization": f"Bearer {second_token}"},
        )
        assert response.status_code == 404

        response = client.put(
            f"/api/businesses/{business_id}",
            headers={"Authorization": f"Bearer {second_token}"},
            json={"business_name": "Hijacked"},
        )
        assert response.status_code == 404
    finally:
        with app.app_context():
            from app.extensions import db

            db.session.execute(
                text("DELETE FROM businesses WHERE id = :business_id"),
                {"business_id": business_id},
            )
            db.session.execute(
                text("DELETE FROM users WHERE id IN (:first, :second)"),
                {"first": first_user_id, "second": second["user"]["id"]},
            )
            db.session.commit()
