import os
from tests.integration_settings import integration_tests_enabled
import uuid
from datetime import datetime, timezone, timedelta

import pytest

from sqlalchemy import text

RUN_INTEGRATION = integration_tests_enabled()


def test_queue_management_routes_are_registered():
    from app import create_app

    app = create_app()
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/api/businesses/<business_id>/queue" in rules
    assert "/api/businesses/<business_id>/queue/call-next" in rules
    assert "/api/businesses/<business_id>/queue/<token_id>/complete" in rules
    assert "/api/businesses/<business_id>/queue/<token_id>/skip" in rules
    assert "/api/businesses/<business_id>/queue/<token_id>/cancel" in rules
    assert "/api/businesses/<business_id>/queue/pause" in rules
    assert "/api/businesses/<business_id>/queue/resume" in rules


@pytest.fixture()
def registered_user(client, app):
    email = f"queueless-test-{uuid.uuid4()}@example.com"
    password = "TestPassword123!"
    response = client.post(
        "/api/auth/register",
        json={"full_name": "Queue Management User", "email": email, "password": password},
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
    response = client.post(
        "/api/businesses",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
        json={"business_name": f"QM Business {uuid.uuid4()}", "business_type": "Clinic"},
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
            {"business_id": business_id, "service_name": f"QM Service {uuid.uuid4()}"},
        ).scalar()
        db.session.commit()

    yield registered_user, business_id, service_id

    with app.app_context():
        from app.extensions import db

        db.session.execute(text("DELETE FROM services WHERE id = :service_id"), {"service_id": service_id})
        db.session.execute(text("DELETE FROM businesses WHERE id = :business_id"), {"business_id": business_id})
        db.session.commit()


@pytest.fixture()
def two_queue_entries(client, app, business_with_service):
    registered_user, business_id, service_id = business_with_service
    ids = []
    for i in range(2):
        response = client.post(
            "/api/public/walk-in",
            json={
                "business_id": business_id,
                "service_id": service_id,
                "customer_name": f"QM Customer {i}",
                "customer_phone": "123",
            },
        )
        assert response.status_code == 201
        ids.append(response.get_json()["queue_token"]["id"])

    yield registered_user, business_id, service_id, ids

    with app.app_context():
        from app.extensions import db

        db.session.execute(text("DELETE FROM queue_tokens WHERE business_id = :business_id"), {"business_id": business_id})
        db.session.commit()


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set QUEUELESS_RUN_INTEGRATION_TESTS=1 to run Supabase integration tests")
def test_get_queue(client, two_queue_entries):
    registered_user, business_id, _, _ = two_queue_entries
    response = client.get(
        f"/api/businesses/{business_id}/queue",
        headers={"Authorization": f"Bearer {registered_user['token']}"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["summary"]["waiting"] == 2
    assert len(data["waiting"]) == 2


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set QUEUELESS_RUN_INTEGRATION_TESTS=1 to run Supabase integration tests")
def test_call_next_and_complete(client, two_queue_entries):
    registered_user, business_id, _, ids = two_queue_entries
    headers = {"Authorization": f"Bearer {registered_user['token']}"}

    call = client.post(f"/api/businesses/{business_id}/queue/call-next", headers=headers)
    assert call.status_code == 200
    called_id = call.get_json()["queue_token"]["id"]
    assert called_id == ids[0]

    busy = client.post(f"/api/businesses/{business_id}/queue/call-next", headers=headers)
    assert busy.status_code == 409

    complete = client.post(f"/api/businesses/{business_id}/queue/{called_id}/complete", headers=headers)
    assert complete.status_code == 200
    assert complete.get_json()["queue_token"]["status"] == "completed"


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set QUEUELESS_RUN_INTEGRATION_TESTS=1 to run Supabase integration tests")
def test_skip_and_cancel(client, two_queue_entries):
    registered_user, business_id, _, ids = two_queue_entries
    headers = {"Authorization": f"Bearer {registered_user['token']}"}

    skip = client.post(f"/api/businesses/{business_id}/queue/{ids[0]}/skip", headers=headers)
    assert skip.status_code == 200
    assert skip.get_json()["queue_token"]["status"] == "skipped"

    cancel = client.post(f"/api/businesses/{business_id}/queue/{ids[1]}/cancel", headers=headers)
    assert cancel.status_code == 200
    assert cancel.get_json()["queue_token"]["status"] == "cancelled"


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set QUEUELESS_RUN_INTEGRATION_TESTS=1 to run Supabase integration tests")
def test_invalid_transitions(client, two_queue_entries):
    registered_user, business_id, _, ids = two_queue_entries
    headers = {"Authorization": f"Bearer {registered_user['token']}"}

    # Complete a waiting token directly is invalid.
    response = client.post(f"/api/businesses/{business_id}/queue/{ids[0]}/complete", headers=headers)
    assert response.status_code == 409

    # Cancel a skipped token is invalid.
    client.post(f"/api/businesses/{business_id}/queue/{ids[0]}/skip", headers=headers)
    response = client.post(f"/api/businesses/{business_id}/queue/{ids[0]}/cancel", headers=headers)
    assert response.status_code == 409


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set QUEUELESS_RUN_INTEGRATION_TESTS=1 to run Supabase integration tests")
def test_queue_management_requires_auth(client, two_queue_entries):
    _, business_id, _, ids = two_queue_entries
    response = client.get(f"/api/businesses/{business_id}/queue")
    assert response.status_code == 401

    response = client.post(f"/api/businesses/{business_id}/queue/call-next")
    assert response.status_code == 401


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set QUEUELESS_RUN_INTEGRATION_TESTS=1 to run Supabase integration tests")
def test_queue_management_unauthorized_business(client, app):
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
        json={"business_name": "Private Queue", "business_type": "Clinic"},
    )
    assert business.status_code == 201
    business_id = business.get_json()["business"]["id"]

    try:
        response = client.get(
            f"/api/businesses/{business_id}/queue",
            headers={"Authorization": f"Bearer {second_data['access_token']}"},
        )
        assert response.status_code == 404
    finally:
        with app.app_context():
            from app.extensions import db

            db.session.execute(text("DELETE FROM businesses WHERE id = :business_id"), {"business_id": business_id})
            db.session.execute(text("DELETE FROM users WHERE id IN (:first, :second)"), {"first": first_data["user"]["id"], "second": second_data["user"]["id"]})
            db.session.commit()


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set QUEUELESS_RUN_INTEGRATION_TESTS=1 to run Supabase integration tests")
def test_pause_resume_without_migration(client, two_queue_entries):
    registered_user, business_id, _, _ = two_queue_entries
    headers = {"Authorization": f"Bearer {registered_user['token']}"}

    pause = client.post(f"/api/businesses/{business_id}/queue/pause", headers=headers)
    resume = client.post(f"/api/businesses/{business_id}/queue/resume", headers=headers)

    # If migration is not applied, endpoints must report the limitation.
    if pause.status_code == 503:
        assert "migration" in pause.get_json()["message"].lower()
        assert resume.status_code == 503
    else:
        assert pause.status_code == 200
        assert resume.status_code == 200
