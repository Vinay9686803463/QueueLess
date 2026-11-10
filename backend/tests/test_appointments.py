import os
import uuid
from datetime import datetime, timezone, timedelta

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
            "full_name": "Appointment Test User",
            "email": email,
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
            text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id}
        )
        db.session.commit()


@pytest.fixture()
def business_with_service(client, app, registered_user):
    business_name = f"Appointment Business {uuid.uuid4()}"
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
                VALUES (:business_id, :service_name, 30, 10.00, TRUE)
                RETURNING id::text
            """),
            {
                "business_id": business_id,
                "service_name": f"Consultation {uuid.uuid4()}",
            },
        ).scalar()
        db.session.commit()

    yield registered_user, business_id, service_id

    with app.app_context():
        from app.extensions import db

        db.session.execute(
            text("DELETE FROM services WHERE id = :service_id"),
            {"service_id": service_id},
        )
        db.session.execute(
            text("DELETE FROM businesses WHERE id = :business_id"),
            {"business_id": business_id},
        )
        db.session.commit()


@pytest.fixture()
def appointment(client, app, business_with_service):
    registered_user, business_id, service_id = business_with_service
    scheduled_at = (
        datetime.now(timezone.utc) + timedelta(days=1)
    ).replace(hour=10, minute=0, second=0, microsecond=0)

    response = client.post(
        "/api/appointments",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
        json={
            "business_id": business_id,
            "service_id": service_id,
            "customer_name": "John Customer",
            "customer_phone": "9876543210",
            "customer_email": "john@example.com",
            "scheduled_at": scheduled_at.isoformat(),
            "notes": "First visit",
        },
    )
    assert response.status_code == 201
    appointment_id = response.get_json()["appointment"]["id"]

    yield registered_user, business_id, service_id, appointment_id, scheduled_at

    with app.app_context():
        from app.extensions import db

        db.session.execute(
            text("DELETE FROM appointments WHERE id = :appointment_id"),
            {"appointment_id": appointment_id},
        )
        db.session.commit()


def test_create_appointment_success(client, business_with_service):
    registered_user, business_id, service_id = business_with_service
    scheduled_at = (
        datetime.now(timezone.utc) + timedelta(days=1)
    ).replace(hour=11, minute=0, second=0, microsecond=0)

    response = client.post(
        "/api/appointments",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
        json={
            "business_id": business_id,
            "service_id": service_id,
            "customer_name": "Jane Customer",
            "customer_phone": "1234567890",
            "scheduled_at": scheduled_at.isoformat(),
        },
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["status"] == "success"
    assert data["appointment"]["status"] == "booked"
    assert data["appointment"]["business_id"] == business_id
    assert data["appointment"]["service_id"] == service_id

    with client.application.app_context():
        from app.extensions import db

        db.session.execute(
            text("DELETE FROM appointments WHERE id = :appointment_id"),
            {"appointment_id": data["appointment"]["id"]},
        )
        db.session.commit()


def test_create_appointment_requires_fields(client, business_with_service):
    registered_user, business_id, service_id = business_with_service
    response = client.post(
        "/api/appointments",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
        json={"business_id": business_id, "service_id": service_id},
    )
    assert response.status_code == 400


def test_create_appointment_requires_auth(client):
    response = client.post(
        "/api/appointments",
        json={
            "business_id": "00000000-0000-0000-0000-000000000000",
            "service_id": "00000000-0000-0000-0000-000000000000",
            "customer_name": "No Auth",
            "customer_phone": "1",
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 401


def test_create_appointment_invalid_business(client, business_with_service):
    registered_user, _, service_id = business_with_service
    response = client.post(
        "/api/appointments",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
        json={
            "business_id": "00000000-0000-0000-0000-000000000000",
            "service_id": service_id,
            "customer_name": "Customer",
            "customer_phone": "1",
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 404


def test_create_appointment_invalid_service(client, business_with_service):
    registered_user, business_id, _ = business_with_service
    response = client.post(
        "/api/appointments",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
        json={
            "business_id": business_id,
            "service_id": "00000000-0000-0000-0000-000000000000",
            "customer_name": "Customer",
            "customer_phone": "1",
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 404


def test_create_appointment_inactive_service(client, app, business_with_service):
    registered_user, business_id, service_id = business_with_service

    with app.app_context():
        from app.extensions import db

        db.session.execute(
            text("UPDATE services SET is_active = FALSE WHERE id = :service_id"),
            {"service_id": service_id},
        )
        db.session.commit()

    response = client.post(
        "/api/appointments",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
        json={
            "business_id": business_id,
            "service_id": service_id,
            "customer_name": "Customer",
            "customer_phone": "1",
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
    )

    with app.app_context():
        from app.extensions import db

        db.session.execute(
            text("UPDATE services SET is_active = TRUE WHERE id = :service_id"),
            {"service_id": service_id},
        )
        db.session.commit()

    assert response.status_code == 404


def test_create_appointment_rejects_past_time(client, business_with_service):
    registered_user, business_id, service_id = business_with_service
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    response = client.post(
        "/api/appointments",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
        json={
            "business_id": business_id,
            "service_id": service_id,
            "customer_name": "Customer",
            "customer_phone": "1",
            "scheduled_at": past,
        },
    )
    assert response.status_code == 400


def test_create_appointment_rejects_outside_hours(client, business_with_service):
    registered_user, business_id, service_id = business_with_service
    outside = (
        datetime.now(timezone.utc) + timedelta(days=1)
    ).replace(hour=18, minute=0, second=0, microsecond=0).isoformat()

    response = client.post(
        "/api/appointments",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
        json={
            "business_id": business_id,
            "service_id": service_id,
            "customer_name": "Customer",
            "customer_phone": "1",
            "scheduled_at": outside,
        },
    )
    assert response.status_code == 400


def test_create_appointment_conflict(client, appointment):
    registered_user, business_id, service_id, _, scheduled_at = appointment
    response = client.post(
        "/api/appointments",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
        json={
            "business_id": business_id,
            "service_id": service_id,
            "customer_name": "Conflicting Customer",
            "customer_phone": "999",
            "scheduled_at": scheduled_at.isoformat(),
        },
    )
    assert response.status_code == 409


def test_list_appointments(client, appointment):
    registered_user, business_id, service_id, appointment_id, _ = appointment
    response = client.get(
        "/api/appointments",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert any(item["id"] == appointment_id for item in data["appointments"])


def test_get_appointment(client, appointment):
    registered_user, business_id, service_id, appointment_id, _ = appointment
    response = client.get(
        f"/api/appointments/{appointment_id}",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["appointment"]["id"] == appointment_id


def test_get_unknown_appointment(client, registered_user):
    response = client.get(
        "/api/appointments/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
    )
    assert response.status_code == 404


def test_update_appointment(client, appointment):
    registered_user, business_id, service_id, appointment_id, scheduled_at = appointment
    new_time = (scheduled_at + timedelta(hours=2)).isoformat()
    response = client.put(
        f"/api/appointments/{appointment_id}",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
        json={
            "scheduled_at": new_time,
            "customer_name": "Updated Customer",
            "status": "confirmed",
        },
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["appointment"]["customer_name"] == "Updated Customer"
    assert data["appointment"]["status"] == "confirmed"


def test_update_appointment_invalid_status(client, appointment):
    registered_user, _, _, appointment_id, _ = appointment
    response = client.put(
        f"/api/appointments/{appointment_id}",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
        json={"status": "not-a-status"},
    )
    assert response.status_code == 400


def test_cancel_appointment(client, appointment):
    registered_user, _, _, appointment_id, _ = appointment
    response = client.delete(
        f"/api/appointments/{appointment_id}",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["appointment"]["status"] == "cancelled"


def test_unauthorized_appointment_access(client, app):
    first_email = f"queueless-test-{uuid.uuid4()}@example.com"
    second_email = f"queueless-test-{uuid.uuid4()}@example.com"
    password = "TestPassword123!"

    first_register = client.post(
        "/api/auth/register",
        json={"full_name": "First User", "email": first_email, "password": password},
    )
    second_register = client.post(
        "/api/auth/register",
        json={"full_name": "Second User", "email": second_email, "password": password},
    )
    assert first_register.status_code == 201
    assert second_register.status_code == 201

    first = first_register.get_json()
    second = second_register.get_json()
    first_user_id = first["user"]["id"]
    second_user_id = second["user"]["id"]

    business_response = client.post(
        "/api/businesses",
        headers={"Authorization": f"Bearer {first['access_token']}"},
        json={"business_name": "Private Clinic", "business_type": "Clinic"},
    )
    assert business_response.status_code == 201
    business_id = business_response.get_json()["business"]["id"]

    with app.app_context():
        from app.extensions import db

        service_id = db.session.execute(
            text("""
                INSERT INTO services (business_id, service_name, duration_minutes, price, is_active)
                VALUES (:business_id, :service_name, 30, 10.00, TRUE)
                RETURNING id::text
            """),
            {"business_id": business_id, "service_name": f"Service {uuid.uuid4()}"},
        ).scalar()
        db.session.commit()

    scheduled_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    appointment_response = client.post(
        "/api/appointments",
        headers={"Authorization": f"Bearer {first['access_token']}"},
        json={
            "business_id": business_id,
            "service_id": service_id,
            "customer_name": "Private Customer",
            "customer_phone": "123",
            "scheduled_at": scheduled_at,
        },
    )
    assert appointment_response.status_code == 201
    appointment_id = appointment_response.get_json()["appointment"]["id"]

    try:
        for method, path in (
            ("GET", f"/api/appointments/{appointment_id}"),
            ("DELETE", f"/api/appointments/{appointment_id}"),
        ):
            response = client.open(path, method=method, headers={"Authorization": f"Bearer {second['access_token']}"})
            assert response.status_code == 404, (method, response.status_code)

        response = client.put(
            f"/api/appointments/{appointment_id}",
            headers={"Authorization": f"Bearer {second['access_token']}"},
            json={"customer_name": "Hijacked"},
        )
        assert response.status_code == 404

        response = client.get(
            "/api/appointments",
            headers={"Authorization": f"Bearer {second['access_token']}"},
        )
        assert response.status_code == 200
        assert all(item["id"] != appointment_id for item in response.get_json()["appointments"])
    finally:
        with app.app_context():
            from app.extensions import db

            db.session.execute(
                text("DELETE FROM appointments WHERE id = :appointment_id"),
                {"appointment_id": appointment_id},
            )
            db.session.execute(
                text("DELETE FROM services WHERE id = :service_id"),
                {"service_id": service_id},
            )
            db.session.execute(
                text("DELETE FROM businesses WHERE id = :business_id"),
                {"business_id": business_id},
            )
            db.session.execute(
                text("DELETE FROM users WHERE id IN (:first, :second)"),
                {"first": first_user_id, "second": second_user_id},
            )
            db.session.commit()
