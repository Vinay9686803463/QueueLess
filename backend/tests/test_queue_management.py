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
    assert "/api/businesses/<business_id>/queue/demo" in rules
    assert "/api/businesses/<business_id>/queue/call-next" in rules
    assert "/api/businesses/<business_id>/queue/<token_id>/complete" in rules
    assert "/api/businesses/<business_id>/queue/<token_id>/skip" in rules
    assert "/api/businesses/<business_id>/queue/<token_id>/cancel" in rules
    assert "/api/businesses/<business_id>/queue/pause" in rules
    assert "/api/businesses/<business_id>/queue/resume" in rules


def test_demo_data_guard_requires_explicit_local_development_opt_in(app):
    from app.routes.queue import _demo_data_enabled

    with app.app_context():
        app.config.update(
            ENV="development",
            QUEUELESS_ENABLE_DEMO_DATA=False,
            SQLALCHEMY_DATABASE_URI="postgresql+psycopg2://localhost/queueless",
        )
        assert not _demo_data_enabled()

        app.config["QUEUELESS_ENABLE_DEMO_DATA"] = True
        assert _demo_data_enabled()

        app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql+psycopg2://db.example/queueless"
        assert not _demo_data_enabled()

        app.config.update(
            ENV="production",
            SQLALCHEMY_DATABASE_URI="postgresql+psycopg2://localhost/queueless",
        )
        assert not _demo_data_enabled()


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
def test_demo_queue_seeding_is_idempotent_and_cleanup_preserves_real_entries(
    client, app, business_with_service, monkeypatch
):
    from app.routes import queue as queue_routes

    registered_user, business_id, service_id = business_with_service
    headers = {"Authorization": f"Bearer {registered_user['token']}"}

    real_entry = client.post(
        "/api/public/walk-in",
        json={
            "business_id": business_id,
            "service_id": service_id,
            "customer_name": "Real Queue Customer",
            "customer_phone": "555-0199",
        },
    )
    assert real_entry.status_code == 201
    real_token_id = real_entry.get_json()["queue_token"]["id"]
    monkeypatch.setattr(queue_routes, "_demo_data_enabled", lambda: True)

    first_seed = client.post(
        f"/api/businesses/{business_id}/queue/demo",
        headers=headers,
    )
    assert first_seed.status_code == 201
    assert first_seed.get_json()["created"] == 12
    assert first_seed.get_json()["total_demo_appointments"] == 12

    appointments = client.get("/api/appointments", headers=headers).get_json()["appointments"]
    demo_appointments = [item for item in appointments if (item.get("notes") or "").startswith("DEMO-GENERATED:")]
    assert len(demo_appointments) == 12
    assert {item["duration_minutes"] for item in demo_appointments} == {60}
    assert len({item["customer_id"] for item in demo_appointments}) == 12
    ordered_appointments = sorted(demo_appointments, key=lambda item: item["scheduled_at"])
    for previous, following in zip(ordered_appointments, ordered_appointments[1:]):
        previous_end = datetime.fromisoformat(previous["scheduled_at"]) + timedelta(minutes=60)
        assert previous_end <= datetime.fromisoformat(following["scheduled_at"])
    demo_date = ordered_appointments[0]["scheduled_at"][:10]

    second_seed = client.post(
        f"/api/businesses/{business_id}/queue/demo",
        headers=headers,
    )
    assert second_seed.status_code == 200
    assert second_seed.get_json()["created"] == 0

    queue = client.get(
        f"/api/businesses/{business_id}/queue?date={demo_date}",
        headers=headers,
    )
    assert queue.status_code == 200
    data = queue.get_json()
    demo_entries = [entry for entry in data["waiting"] if entry["is_demo"]]
    real_entries = [entry for entry in data["waiting"] if not entry["is_demo"]]
    assert len(demo_entries) == 12
    assert len({entry["id"] for entry in demo_entries}) == 12
    assert len({entry["tracking_code"] for entry in demo_entries}) == 12
    assert all(entry["customer_name"].startswith("DEMO · ") for entry in demo_entries)
    assert len(demo_entries) == 12
    today_queue = client.get(
        f"/api/businesses/{business_id}/queue?date={queue_routes.queue_date_today().isoformat()}",
        headers=headers,
    ).get_json()
    real_entries = [entry for entry in today_queue["waiting"] if entry["id"] == real_token_id]
    assert len(real_entries) == 1

    removal = client.delete(
        f"/api/businesses/{business_id}/queue/demo",
        headers=headers,
    )
    assert removal.status_code == 200
    assert removal.get_json()["removed"] == 12

    with app.app_context():
        from app.extensions import db

        remaining_ids = db.session.execute(
            text("""
                SELECT id::text
                FROM queue_tokens
                WHERE business_id = :business_id
            """),
            {"business_id": business_id},
        ).scalars().all()
    assert remaining_ids == [real_token_id]


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
