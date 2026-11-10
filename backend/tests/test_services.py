import os
from tests.integration_settings import integration_tests_enabled
import uuid

import pytest

from sqlalchemy import text

from app.routes.services import validate_service_data, serialize_service


def test_validate_service_data_requires_name_on_create():
    assert validate_service_data({}, creating=True) == "Service name is required"


def test_validate_service_data_rejects_invalid_duration():
    assert validate_service_data({"service_name": "Haircut", "duration_minutes": 0}) == "Duration must be a whole number" or \
           validate_service_data({"service_name": "Haircut", "duration_minutes": 0}) == "Duration must be greater than zero"


def test_validate_service_data_rejects_negative_price():
    assert validate_service_data({"service_name": "Haircut", "price": -1}) == "Price cannot be negative"


def test_validate_service_data_rejects_invalid_is_active():
    assert validate_service_data({"service_name": "Haircut", "is_active": "yes"}) == "is_active must be true or false"


def test_validate_service_data_accepts_valid_payload():
    assert validate_service_data(
        {
            "service_name": "Haircut",
            "description": "Basic haircut",
            "duration_minutes": 30,
            "price": 10.5,
            "is_active": True,
        },
        creating=True,
    ) is None


def test_serialize_service_formats_timestamps():
    from datetime import datetime, timezone

    row = {
        "id": "service-id",
        "business_id": "business-id",
        "service_name": "Haircut",
        "description": "Basic haircut",
        "duration_minutes": 30,
        "price": 10.5,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    service = serialize_service(row)
    assert service["id"] == "service-id"
    assert "T" in service["created_at"]
    assert "T" in service["updated_at"]


def test_service_routes_are_registered():
    from app import create_app

    app = create_app()
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/api/businesses/<business_id>/services" in rules
    assert "/api/businesses/<business_id>/services/<service_id>" in rules


RUN_INTEGRATION = integration_tests_enabled()
pytestmark_integration = [
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
        json={"full_name": "Service Test User", "email": email, "password": password},
    )
    assert response.status_code == 201
    data = response.get_json()
    yield {"email": email, "password": password, "user_id": data["user"]["id"], "token": data["access_token"]}

    with app.app_context():
        from app.extensions import db

        db.session.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": data["user"]["id"]})
        db.session.commit()


@pytest.fixture()
def business(client, app, registered_user):
    response = client.post(
        "/api/businesses",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
        json={"business_name": f"Service Business {uuid.uuid4()}", "business_type": "Salon"},
    )
    assert response.status_code == 201
    business_id = response.get_json()["business"]["id"]
    yield registered_user, business_id

    with app.app_context():
        from app.extensions import db

        db.session.execute(text("DELETE FROM services WHERE business_id = :business_id"), {"business_id": business_id})
        db.session.execute(text("DELETE FROM businesses WHERE id = :business_id"), {"business_id": business_id})
        db.session.commit()


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set QUEUELESS_RUN_INTEGRATION_TESTS=1 to run Supabase integration tests")
def test_service_crud_integration(client, business):
    registered_user, business_id = business
    headers = {"Authorization": f"Bearer {registered_user['token']}"}

    create = client.post(
        f"/api/businesses/{business_id}/services",
        headers=headers,
        json={
            "service_name": f" haircut {uuid.uuid4()} ",
            "description": "Basic haircut",
            "duration_minutes": 30,
            "price": 10.5,
        },
    )
    assert create.status_code == 201
    service = create.get_json()["service"]
    assert service["service_name"].startswith("haircut")
    assert service["business_id"] == business_id
    service_id = service["id"]

    listing = client.get(f"/api/businesses/{business_id}/services", headers=headers)
    assert listing.status_code == 200
    assert any(item["id"] == service_id for item in listing.get_json()["services"])

    fetched = client.get(f"/api/businesses/{business_id}/services/{service_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.get_json()["service"]["id"] == service_id

    updated = client.put(
        f"/api/businesses/{business_id}/services/{service_id}",
        headers=headers,
        json={"service_name": f"Updated {uuid.uuid4()}", "duration_minutes": 45, "is_active": False},
    )
    assert updated.status_code == 200
    assert updated.get_json()["service"]["duration_minutes"] == 45
    assert updated.get_json()["service"]["is_active"] is False

    deactivated = client.delete(f"/api/businesses/{business_id}/services/{service_id}", headers=headers)
    assert deactivated.status_code == 200
    assert deactivated.get_json()["service"]["is_active"] is False


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set QUEUELESS_RUN_INTEGRATION_TESTS=1 to run Supabase integration tests")
def test_service_requires_auth(client, business):
    _, business_id = business
    response = client.post(
        f"/api/businesses/{business_id}/services",
        json={"service_name": "No Auth", "duration_minutes": 10},
    )
    assert response.status_code == 401


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set QUEUELESS_RUN_INTEGRATION_TESTS=1 to run Supabase integration tests")
def test_service_rejects_invalid_business(client, registered_user):
    response = client.post(
        "/api/businesses/00000000-0000-0000-0000-000000000000/services",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
        json={"service_name": "Invalid Business", "duration_minutes": 10},
    )
    assert response.status_code == 404


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set QUEUELESS_RUN_INTEGRATION_TESTS=1 to run Supabase integration tests")
def test_service_deactivation_preserves_appointments_and_tokens(client, app, business):
    registered_user, business_id = business
    headers = {"Authorization": f"Bearer {registered_user['token']}"}

    service_response = client.post(
        f"/api/businesses/{business_id}/services",
        headers=headers,
        json={"service_name": f"Protected Service {uuid.uuid4()}", "duration_minutes": 20},
    )
    assert service_response.status_code == 201
    service_id = service_response.get_json()["service"]["id"]

    with app.app_context():
        from app.extensions import db

        appointment_id = db.session.execute(
            text("""
                INSERT INTO appointments (business_id, service_id, customer_name, customer_phone, scheduled_at, status)
                VALUES (:business_id, :service_id, 'Protected Customer', '123', NOW() + INTERVAL '1 day', 'booked')
                RETURNING id::text
            """),
            {"business_id": business_id, "service_id": service_id},
        ).scalar()
        token_id = db.session.execute(
            text("""
                INSERT INTO queue_tokens (business_id, service_id, customer_name, customer_phone, token_number, status)
                VALUES (:business_id, :service_id, 'Protected Customer', '123', 1, 'waiting')
                RETURNING id::text
            """),
            {"business_id": business_id, "service_id": service_id},
        ).scalar()
        db.session.commit()

    deactivate = client.delete(f"/api/businesses/{business_id}/services/{service_id}", headers=headers)
    assert deactivate.status_code == 200
    assert deactivate.get_json()["service"]["is_active"] is False

    with app.app_context():
        from app.extensions import db

        appointment_exists = db.session.execute(
            text("SELECT COUNT(*) FROM appointments WHERE id = :appointment_id"),
            {"appointment_id": appointment_id},
        ).scalar()
        token_exists = db.session.execute(
            text("SELECT COUNT(*) FROM queue_tokens WHERE id = :token_id"),
            {"token_id": token_id},
        ).scalar()

    assert appointment_exists == 1
    assert token_exists == 1

    with app.app_context():
        from app.extensions import db

        db.session.execute(text("DELETE FROM queue_tokens WHERE id = :token_id"), {"token_id": token_id})
        db.session.execute(text("DELETE FROM appointments WHERE id = :appointment_id"), {"appointment_id": appointment_id})
        db.session.execute(text("DELETE FROM services WHERE id = :service_id"), {"service_id": service_id})
        db.session.commit()
