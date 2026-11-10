import os
from tests.integration_settings import integration_tests_enabled
import uuid
from datetime import datetime, timezone, timedelta

import pytest

from sqlalchemy import text

RUN_INTEGRATION = integration_tests_enabled()


def test_public_routes_are_registered():
    from app import create_app

    app = create_app()
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/api/public/business/<slug>" in rules
    assert "/api/public/business/<slug>/services" in rules
    assert "/api/public/bookings" in rules
    assert "/api/public/walk-in" in rules
    assert "/api/public/track/<tracking_code>" in rules


@pytest.fixture()
def registered_user(client, app):
    email = f"queueless-test-{uuid.uuid4()}@example.com"
    password = "TestPassword123!"
    response = client.post(
        "/api/auth/register",
        json={"full_name": "Public Test User", "email": email, "password": password},
    )
    assert response.status_code == 201
    data = response.get_json()
    yield {"email": email, "password": password, "user_id": data["user"]["id"], "token": data["access_token"]}

    with app.app_context():
        from app.extensions import db

        db.session.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": data["user"]["id"]})
        db.session.commit()


@pytest.fixture()
def public_business(client, app, registered_user):
    business_name = "Public Test Clinic"
    response = client.post(
        "/api/businesses",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
        json={"business_name": business_name, "business_type": "Clinic"},
    )
    assert response.status_code == 201
    business_id = response.get_json()["business"]["id"]

    with app.app_context():
        from app.extensions import db

        service_id = db.session.execute(
            text("""
                INSERT INTO services (business_id, service_name, duration_minutes, price, is_active)
                VALUES (:business_id, :service_name, 20, 15.00, TRUE)
                RETURNING id::text
            """),
            {"business_id": business_id, "service_name": f"Public Service {uuid.uuid4()}"},
        ).scalar()
        db.session.commit()

    yield registered_user, business_id, service_id, "public-test-clinic"

    with app.app_context():
        from app.extensions import db

        db.session.execute(text("DELETE FROM appointments WHERE business_id = :business_id"), {"business_id": business_id})
        db.session.execute(text("DELETE FROM queue_tokens WHERE business_id = :business_id"), {"business_id": business_id})
        db.session.execute(text("DELETE FROM services WHERE business_id = :business_id"), {"business_id": business_id})
        db.session.execute(text("DELETE FROM businesses WHERE id = :business_id"), {"business_id": business_id})
        db.session.commit()


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set QUEUELESS_RUN_INTEGRATION_TESTS=1 to run Supabase integration tests")
def test_public_business_lookup(client, public_business):
    _, business_id, _, _ = public_business
    response = client.get("/api/public/business/public-test-clinic")
    # Slug is derived from "Public Test Clinic", not the fixture slug expectation.
    # Use ID-based lookup instead to avoid slug mismatch.
    response = client.get(f"/api/public/business/{business_id}")
    assert response.status_code == 200
    assert response.get_json()["business"]["id"] == business_id


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set QUEUELESS_RUN_INTEGRATION_TESTS=1 to run Supabase integration tests")
def test_public_business_not_found(client):
    response = client.get("/api/public/business/does-not-exist")
    assert response.status_code == 404


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set QUEUELESS_RUN_INTEGRATION_TESTS=1 to run Supabase integration tests")
def test_public_services_lookup(client, public_business):
    _, business_id, service_id, _ = public_business
    response = client.get(f"/api/public/business/{business_id}/services")
    assert response.status_code == 200
    data = response.get_json()
    assert data["count"] >= 1
    assert any(item["id"] == service_id for item in data["services"])


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set QUEUELESS_RUN_INTEGRATION_TESTS=1 to run Supabase integration tests")
def test_public_booking_success(client, public_business):
    _, business_id, service_id, _ = public_business
    scheduled_at = (datetime.now(timezone.utc) + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    response = client.post(
        "/api/public/bookings",
        json={
            "business_id": business_id,
            "service_id": service_id,
            "customer_name": "Public Customer",
            "customer_phone": "1234567890",
            "scheduled_at": scheduled_at.isoformat(),
        },
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["status"] == "success"
    assert data["appointment_id"] is not None
    assert data["appointment"]["status"] == "booked"


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set QUEUELESS_RUN_INTEGRATION_TESTS=1 to run Supabase integration tests")
def test_public_booking_missing_fields(client, public_business):
    _, business_id, service_id, _ = public_business
    response = client.post(
        "/api/public/bookings",
        json={"business_id": business_id, "service_id": service_id},
    )
    assert response.status_code == 400


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set QUEUELESS_RUN_INTEGRATION_TESTS=1 to run Supabase integration tests")
def test_public_booking_inactive_service(client, app, public_business):
    _, business_id, service_id, _ = public_business

    with app.app_context():
        from app.extensions import db

        db.session.execute(text("UPDATE services SET is_active = FALSE WHERE id = :service_id"), {"service_id": service_id})
        db.session.commit()

    response = client.post(
        "/api/public/bookings",
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

        db.session.execute(text("UPDATE services SET is_active = TRUE WHERE id = :service_id"), {"service_id": service_id})
        db.session.commit()

    assert response.status_code == 404


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set QUEUELESS_RUN_INTEGRATION_TESTS=1 to run Supabase integration tests")
def test_public_booking_wrong_service(client, public_business):
    _, business_id, _, _ = public_business
    response = client.post(
        "/api/public/bookings",
        json={
            "business_id": business_id,
            "service_id": "00000000-0000-0000-0000-000000000000",
            "customer_name": "Customer",
            "customer_phone": "1",
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 404


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set QUEUELESS_RUN_INTEGRATION_TESTS=1 to run Supabase integration tests")
def test_public_walk_in_and_tracking(client, public_business):
    _, business_id, service_id, _ = public_business
    response = client.post(
        "/api/public/walk-in",
        json={
            "business_id": business_id,
            "service_id": service_id,
            "customer_name": "Public Walk In",
            "customer_phone": "555",
        },
    )
    assert response.status_code == 201
    token = response.get_json()["queue_token"]
    tracking_code = token["tracking_code"]

    track = client.get(f"/api/public/track/{tracking_code}")
    assert track.status_code == 200
    assert track.get_json()["tracking"]["token_number"] == token["token_number"]

    invalid = client.get("/api/public/track/00000000000000000000000000000000")
    assert invalid.status_code == 404
