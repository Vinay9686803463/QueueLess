import os
from tests.integration_settings import integration_tests_enabled
import uuid
from datetime import datetime, timezone, timedelta

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
    response = client.post(
        "/api/auth/register",
        json={"full_name": "Queue Test User", "email": email, "password": password},
    )
    assert response.status_code == 201
    data = response.get_json()
    yield {"email": email, "password": password, "user_id": data["user"]["id"], "token": data["access_token"]}

    with app.app_context():
        from app.extensions import db

        db.session.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": data["user"]["id"]})
        db.session.commit()


@pytest.fixture()
def business_with_service(client, app, registered_user):
    business_name = f"Queue Business {uuid.uuid4()}"
    response = client.post(
        "/api/businesses",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
        json={
            "business_name": business_name,
            "business_type": "Clinic",
            "opening_time": "09:00",
            "closing_time": "17:00",
        },
    )
    assert response.status_code == 201
    business_id = response.get_json()["business"]["id"]

    with app.app_context():
        from app.extensions import db

        service_id = db.session.execute(
            text("""
                INSERT INTO services (business_id, service_name, duration_minutes, price, is_active)
                VALUES (:business_id, :service_name, 15, 10.00, TRUE)
                RETURNING id::text
            """),
            {"business_id": business_id, "service_name": f"Service {uuid.uuid4()}"},
        ).scalar()
        db.session.commit()

    yield registered_user, business_id, service_id

    with app.app_context():
        from app.extensions import db

        db.session.execute(text("DELETE FROM services WHERE id = :service_id"), {"service_id": service_id})
        db.session.execute(text("DELETE FROM businesses WHERE id = :business_id"), {"business_id": business_id})
        db.session.commit()


@pytest.fixture()
def appointment(client, app, business_with_service):
    registered_user, business_id, service_id = business_with_service
    scheduled_at = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )

    response = client.post(
        "/api/appointments",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
        json={
            "business_id": business_id,
            "service_id": service_id,
            "customer_name": "Appointment Customer",
            "customer_phone": "1234567890",
            "scheduled_at": scheduled_at.isoformat(),
        },
    )
    assert response.status_code == 201
    appointment_id = response.get_json()["appointment"]["id"]

    yield registered_user, business_id, service_id, appointment_id, scheduled_at

    with app.app_context():
        from app.extensions import db

        db.session.execute(text("DELETE FROM queue_tokens WHERE appointment_id = :appointment_id"), {"appointment_id": appointment_id})
        db.session.execute(text("DELETE FROM appointments WHERE id = :appointment_id"), {"appointment_id": appointment_id})
        db.session.commit()


def test_check_in_appointment_success(client, appointment):
    registered_user, business_id, service_id, appointment_id, _ = appointment
    response = client.post(
        f"/api/appointments/{appointment_id}/check-in",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["status"] == "success"
    token = data["queue_token"]
    assert token["status"] == "waiting"
    assert token["business_id"] == business_id
    assert token["service_id"] == service_id
    assert token["appointment_id"] == appointment_id
    assert token["token_number"] >= 1
    assert len(token["tracking_code"]) == 32

    with client.application.app_context():
        from app.extensions import db

        db.session.execute(text("DELETE FROM queue_tokens WHERE appointment_id = :appointment_id"), {"appointment_id": appointment_id})
        db.session.commit()


def test_duplicate_check_in(client, appointment):
    registered_user, _, _, appointment_id, _ = appointment
    first = client.post(
        f"/api/appointments/{appointment_id}/check-in",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
    )
    assert first.status_code == 201

    second = client.post(
        f"/api/appointments/{appointment_id}/check-in",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
    )
    assert second.status_code == 409

    with client.application.app_context():
        from app.extensions import db

        db.session.execute(text("DELETE FROM queue_tokens WHERE appointment_id = :appointment_id"), {"appointment_id": appointment_id})
        db.session.commit()


def test_check_in_invalid_appointment(client, registered_user):
    response = client.post(
        "/api/appointments/00000000-0000-0000-0000-000000000000/check-in",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
    )
    assert response.status_code == 404


def test_check_in_requires_auth(client, appointment):
    _, _, _, appointment_id, _ = appointment
    response = client.post(f"/api/appointments/{appointment_id}/check-in")
    assert response.status_code == 401


def test_check_in_other_users_appointment(client, app):
    first_email = f"queueless-test-{uuid.uuid4()}@example.com"
    second_email = f"queueless-test-{uuid.uuid4()}@example.com"
    password = "TestPassword123!"

    first = client.post("/api/auth/register", json={"full_name": "First", "email": first_email, "password": password})
    second = client.post("/api/auth/register", json={"full_name": "Second", "email": second_email, "password": password})
    assert first.status_code == 201 and second.status_code == 201
    first_data = first.get_json()
    second_data = second.get_json()

    business = client.post(
        "/api/businesses",
        headers={"Authorization": f"Bearer {first_data['access_token']}"},
        json={"business_name": "Private Clinic", "business_type": "Clinic"},
    )
    assert business.status_code == 201
    business_id = business.get_json()["business"]["id"]

    with app.app_context():
        from app.extensions import db

        service_id = db.session.execute(
            text("""
                INSERT INTO services (business_id, service_name, duration_minutes, price, is_active)
                VALUES (:business_id, :service_name, 15, 10.00, TRUE)
                RETURNING id::text
            """),
            {"business_id": business_id, "service_name": f"Service {uuid.uuid4()}"},
        ).scalar()
        db.session.commit()

    scheduled_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    appointment = client.post(
        "/api/appointments",
        headers={"Authorization": f"Bearer {first_data['access_token']}"},
        json={
            "business_id": business_id,
            "service_id": service_id,
            "customer_name": "Private Customer",
            "customer_phone": "123",
            "scheduled_at": scheduled_at,
        },
    )
    assert appointment.status_code == 201
    appointment_id = appointment.get_json()["appointment"]["id"]

    try:
        response = client.post(
            f"/api/appointments/{appointment_id}/check-in",
            headers={"Authorization": f"Bearer {second_data['access_token']}"},
        )
        assert response.status_code == 404
    finally:
        with app.app_context():
            from app.extensions import db

            db.session.execute(text("DELETE FROM queue_tokens WHERE appointment_id = :appointment_id"), {"appointment_id": appointment_id})
            db.session.execute(text("DELETE FROM appointments WHERE id = :appointment_id"), {"appointment_id": appointment_id})
            db.session.execute(text("DELETE FROM services WHERE id = :service_id"), {"service_id": service_id})
            db.session.execute(text("DELETE FROM businesses WHERE id = :business_id"), {"business_id": business_id})
            db.session.execute(text("DELETE FROM users WHERE id IN (:first, :second)"), {"first": first_data["user"]["id"], "second": second_data["user"]["id"]})
            db.session.commit()


def test_walk_in_success(client, business_with_service):
    _, business_id, service_id = business_with_service
    response = client.post(
        "/api/public/walk-in",
        json={
            "business_id": business_id,
            "service_id": service_id,
            "customer_name": "Walk In Customer",
            "customer_phone": "9999999999",
        },
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["status"] == "success"
    token = data["queue_token"]
    assert token["status"] == "waiting"
    assert token["appointment_id"] is None
    assert token["business_id"] == business_id
    assert token["service_id"] == service_id
    assert len(token["tracking_code"]) == 32
    assert "estimated_wait_minutes" in token

    with client.application.app_context():
        from app.extensions import db

        db.session.execute(text("DELETE FROM queue_tokens WHERE id = :token_id"), {"token_id": token["id"]})
        db.session.commit()


def test_walk_in_invalid_business(client, business_with_service):
    _, _, service_id = business_with_service
    response = client.post(
        "/api/public/walk-in",
        json={
            "business_id": "00000000-0000-0000-0000-000000000000",
            "service_id": service_id,
            "customer_name": "Customer",
            "customer_phone": "1",
        },
    )
    assert response.status_code == 404


def test_walk_in_invalid_service(client, business_with_service):
    _, business_id, _ = business_with_service
    response = client.post(
        "/api/public/walk-in",
        json={
            "business_id": business_id,
            "service_id": "00000000-0000-0000-0000-000000000000",
            "customer_name": "Customer",
            "customer_phone": "1",
        },
    )
    assert response.status_code == 404


def test_walk_in_inactive_service(client, app, business_with_service):
    _, business_id, service_id = business_with_service

    with app.app_context():
        from app.extensions import db

        db.session.execute(text("UPDATE services SET is_active = FALSE WHERE id = :service_id"), {"service_id": service_id})
        db.session.commit()

    response = client.post(
        "/api/public/walk-in",
        json={
            "business_id": business_id,
            "service_id": service_id,
            "customer_name": "Customer",
            "customer_phone": "1",
        },
    )

    with app.app_context():
        from app.extensions import db

        db.session.execute(text("UPDATE services SET is_active = TRUE WHERE id = :service_id"), {"service_id": service_id})
        db.session.commit()

    assert response.status_code == 404


def test_walk_in_missing_customer_info(client, business_with_service):
    _, business_id, service_id = business_with_service
    response = client.post(
        "/api/public/walk-in",
        json={
            "business_id": business_id,
            "service_id": service_id,
            "customer_name": "",
            "customer_phone": "1",
        },
    )
    assert response.status_code == 400


def test_track_valid_code(client, business_with_service):
    _, business_id, service_id = business_with_service
    create = client.post(
        "/api/public/walk-in",
        json={
            "business_id": business_id,
            "service_id": service_id,
            "customer_name": "Tracked Customer",
            "customer_phone": "555",
        },
    )
    assert create.status_code == 201
    token = create.get_json()["queue_token"]
    tracking_code = token["tracking_code"]

    response = client.get(f"/api/public/track/{tracking_code}")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    tracking = data["tracking"]
    assert tracking["token_number"] == token["token_number"]
    assert tracking["queue_status"] == "waiting"
    assert tracking["business_name"] is not None
    assert tracking["service_name"] is not None
    assert "customers_ahead" in tracking
    assert "estimated_wait_minutes" in tracking

    with client.application.app_context():
        from app.extensions import db

        db.session.execute(text("DELETE FROM queue_tokens WHERE id = :token_id"), {"token_id": token["id"]})
        db.session.commit()


def test_track_invalid_code(client):
    response = client.get("/api/public/track/00000000000000000000000000000000")
    assert response.status_code == 404


def test_duplicate_token_prevention(client, business_with_service):
    _, business_id, service_id = business_with_service
    first = client.post(
        "/api/public/walk-in",
        json={
            "business_id": business_id,
            "service_id": service_id,
            "customer_name": "First",
            "customer_phone": "1",
        },
    )
    second = client.post(
        "/api/public/walk-in",
        json={
            "business_id": business_id,
            "service_id": service_id,
            "customer_name": "Second",
            "customer_phone": "2",
        },
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.get_json()["queue_token"]["token_number"] != second.get_json()["queue_token"]["token_number"]

    with client.application.app_context():
        from app.extensions import db

        db.session.execute(
            text("DELETE FROM queue_tokens WHERE business_id = :business_id"),
            {"business_id": business_id},
        )
        db.session.commit()
