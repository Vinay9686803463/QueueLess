from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

from app.extensions import db
from app.routes import appointments
from app.routes.auth import generate_token


USER_ID = str(uuid4())
BUSINESS_ONE = str(uuid4())
BUSINESS_TWO = str(uuid4())


class FakeResult:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows

    def fetchall(self):
        return self.rows


@pytest.fixture()
def appointment_api(app, monkeypatch):
    app.config["TESTING"] = True
    queries = []
    appointment_rows = []
    accessible_business_ids = {BUSINESS_ONE, BUSINESS_TWO}
    database_error = None

    def execute(statement, params=None):
        nonlocal database_error
        sql = str(statement)
        params = params or {}
        queries.append((sql, params))

        if "FROM users" in sql:
            return FakeResult([{
                "id": USER_ID,
                "full_name": "Test Admin",
                "email": "admin@example.test",
                "phone": None,
                "is_active": True,
            }])
        if "FROM businesses" in sql and "business_staff" in sql:
            return FakeResult([(business_id,) for business_id in accessible_business_ids])
        if "FROM appointments" in sql:
            if database_error:
                raise database_error
            filtered = [
                appointment for appointment in appointment_rows
                if appointment["business_id"] in params["business_ids"]
            ]
            return FakeResult(filtered)
        raise AssertionError(f"Unexpected SQL in appointment API test: {sql}")

    def set_database_error(error):
        nonlocal database_error
        database_error = error

    monkeypatch.setattr(db.session, "execute", execute)
    with app.app_context():
        token = generate_token(USER_ID)

    return {
        "app": app,
        "token": token,
        "queries": queries,
        "appointment_rows": appointment_rows,
        "accessible_business_ids": accessible_business_ids,
        "set_database_error": set_database_error,
    }


def test_list_appointments_filters_by_selected_authorized_business(appointment_api):
    scheduled_at = datetime(2030, 1, 2, 10, tzinfo=timezone.utc)
    appointment_api["appointment_rows"].extend([
        {
            "id": str(uuid4()),
            "business_id": BUSINESS_ONE,
            "scheduled_at": scheduled_at,
            "customer_name": "First Business Customer",
            "customer_phone": "111",
            "customer_email": None,
            "service_name": "First Service",
            "duration_minutes": 30,
            "business_name": "First Business",
        },
        {
            "id": str(uuid4()),
            "business_id": BUSINESS_TWO,
            "scheduled_at": scheduled_at,
            "customer_name": "Second Business Customer",
            "customer_phone": "222",
            "customer_email": None,
            "service_name": "Second Service",
            "duration_minutes": 45,
            "business_name": "Second Business",
        },
    ])

    response = appointment_api["app"].test_client().get(
        f"/api/appointments?business_id={BUSINESS_ONE}",
        headers={"Authorization": f"Bearer {appointment_api['token']}"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["count"] == 1
    assert data["appointments"][0]["business_id"] == BUSINESS_ONE
    assert data["appointments"][0]["customer_email"] is None
    assert data["appointments"][0]["scheduled_at"] == scheduled_at.isoformat()

    query, params = next(
        (sql, params) for sql, params in appointment_api["queries"]
        if "FROM appointments" in sql
    )
    assert params["business_ids"] == (BUSINESS_ONE,)
    assert "appointments.business_id::text IN" in query
    assert "business_ids" in query
    assert "appointments.duration_minutes" not in query
    assert "s.duration_minutes" in query


def test_list_appointments_returns_empty_for_user_without_businesses(appointment_api):
    appointment_api["accessible_business_ids"].clear()
    response = appointment_api["app"].test_client().get(
        "/api/appointments",
        headers={"Authorization": f"Bearer {appointment_api['token']}"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "success",
        "count": 0,
        "appointments": [],
    }
    assert not any("FROM appointments" in sql for sql, _ in appointment_api["queries"])


def test_list_appointments_returns_empty_for_selected_business_with_no_appointments(
    appointment_api,
):
    response = appointment_api["app"].test_client().get(
        f"/api/appointments?business_id={BUSINESS_ONE}",
        headers={"Authorization": f"Bearer {appointment_api['token']}"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "success",
        "count": 0,
        "appointments": [],
    }


def test_list_appointments_rejects_unauthorized_business(appointment_api):
    response = appointment_api["app"].test_client().get(
        f"/api/appointments?business_id={str(uuid4())}",
        headers={"Authorization": f"Bearer {appointment_api['token']}"},
    )

    assert response.status_code == 404
    assert response.get_json()["status"] == "error"
    assert not any("FROM appointments" in sql for sql, _ in appointment_api["queries"])


def test_list_appointments_requires_authentication(appointment_api):
    response = appointment_api["app"].test_client().get("/api/appointments")

    assert response.status_code == 401
    assert response.get_json()["message"] == "Authentication token is required"


def test_list_appointments_reports_database_failure_instead_of_empty_list(
    appointment_api, caplog
):
    appointment_api["set_database_error"](
        OperationalError("SELECT appointments", {}, Exception("database unavailable"))
    )

    response = appointment_api["app"].test_client().get(
        f"/api/appointments?business_id={BUSINESS_ONE}",
        headers={"Authorization": f"Bearer {appointment_api['token']}"},
    )

    assert response.status_code == 500
    assert response.get_json() == {
        "status": "error",
        "message": "Unable to retrieve appointments",
    }
    assert "Appointment listing failed" in caplog.text
    assert any(
        record.exc_info
        for record in caplog.records
        if record.message == "Appointment listing failed"
    )
