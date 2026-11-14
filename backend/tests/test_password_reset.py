import uuid

import pytest
from sqlalchemy import text

from tests.integration_settings import integration_tests_enabled

RUN_INTEGRATION = integration_tests_enabled()
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not RUN_INTEGRATION,
        reason="Set QUEUELESS_RUN_INTEGRATION_TESTS=1 to run Supabase integration tests",
    ),
]


@pytest.fixture()
def reset_accounts(client, app):
    unique = uuid.uuid4()
    admin_email = f"reset-admin-{unique}@example.com"
    customer_email = f"reset-customer-{unique}@example.com"
    old_password = "OldPassword123!"
    admin = client.post(
        "/api/auth/register",
        json={
            "full_name": "Reset Admin",
            "email": admin_email,
            "password": old_password,
        },
    )
    customer = client.post(
        "/api/customer-auth/register",
        json={
            "full_name": "Reset Customer",
            "email": customer_email,
            "password": old_password,
        },
    )
    assert admin.status_code == 201
    assert customer.status_code == 201

    account_data = {
        "admin_email": admin_email,
        "customer_email": customer_email,
        "admin_id": admin.get_json()["user"]["id"],
        "customer_id": customer.get_json()["customer"]["id"],
        "old_password": old_password,
    }
    yield account_data

    with app.app_context():
        from app.extensions import db

        db.session.execute(
            text("DELETE FROM users WHERE id = :id"),
            {"id": account_data["admin_id"]},
        )
        db.session.execute(
            text("DELETE FROM customers WHERE id = :id"),
            {"id": account_data["customer_id"]},
        )
        db.session.commit()


def test_admin_and_customer_resets_are_isolated_and_single_use(
    client, app, reset_accounts, monkeypatch
):
    from app.utils import password_reset

    codes = {}

    def capture_email(email, otp, account_type):
        codes[account_type] = otp

    monkeypatch.setattr(password_reset, "_send_otp_email", capture_email)
    monkeypatch.setitem(app.config, "MAIL_SERVER", "smtp.test")
    monkeypatch.setitem(app.config, "MAIL_PORT", 587)
    monkeypatch.setitem(app.config, "MAIL_USERNAME", "noreply@example.com")
    monkeypatch.setitem(app.config, "MAIL_PASSWORD", "test-app-password")
    monkeypatch.setitem(app.config, "MAIL_DEFAULT_SENDER", "noreply@example.com")
    monkeypatch.setitem(app.config, "MAIL_USE_TLS", True)
    monkeypatch.setitem(app.config, "MAIL_USE_SSL", False)
    accounts = reset_accounts

    for portal, prefix, email in (
        ("admin", "auth", accounts["admin_email"]),
        ("customer", "customer-auth", accounts["customer_email"]),
    ):
        response = client.post(
            f"/api/{prefix}/forgot-password",
            json={"email": email},
        )
        assert response.status_code == 202
        assert response.get_json()["email_sent"] is True
        assert "otp" not in response.get_json()
        assert portal in codes

    admin_code = codes["admin"]
    customer_code = codes["customer"]
    assert client.post(
        "/api/auth/forgot-password",
        json={"email": accounts["admin_email"]},
    ).status_code == 429
    wrong_code = f"{(int(admin_code) + 1) % 1_000_000:06d}"
    assert client.post(
        "/api/auth/verify-otp",
        json={"email": accounts["admin_email"], "otp": wrong_code},
    ).status_code == 400
    assert client.post(
        "/api/customer-auth/verify-otp",
        json={"email": accounts["admin_email"], "otp": admin_code},
    ).status_code == 400
    assert client.post(
        "/api/auth/verify-otp",
        json={"email": accounts["customer_email"], "otp": customer_code},
    ).status_code == 400

    admin_verification = client.post(
        "/api/auth/verify-otp",
        json={"email": accounts["admin_email"], "otp": admin_code},
    )
    customer_verification = client.post(
        "/api/customer-auth/verify-otp",
        json={"email": accounts["customer_email"], "otp": customer_code},
    )
    assert admin_verification.status_code == 200
    assert customer_verification.status_code == 200
    admin_authorization = admin_verification.get_json()["reset_token"]
    customer_authorization = customer_verification.get_json()["reset_token"]

    assert client.post(
        "/api/customer-auth/reset-password",
        json={"token": admin_authorization, "password": "NewAdminPassword123!"},
    ).status_code == 400
    assert client.post(
        "/api/auth/reset-password",
        json={"token": customer_authorization, "password": "NewCustomerPassword123!"},
    ).status_code == 400

    assert client.post(
        "/api/auth/verify-otp",
        json={"email": accounts["admin_email"], "otp": admin_code},
    ).status_code == 400
    assert client.post(
        "/api/customer-auth/verify-otp",
        json={"email": accounts["customer_email"], "otp": customer_code},
    ).status_code == 400

    admin_reset = client.post(
        "/api/auth/reset-password",
        json={"token": admin_authorization, "password": "NewAdminPassword123!"},
    )
    customer_reset = client.post(
        "/api/customer-auth/reset-password",
        json={"token": customer_authorization, "password": "NewCustomerPassword123!"},
    )
    assert admin_reset.status_code == 200
    assert customer_reset.status_code == 200
    assert client.post(
        "/api/auth/reset-password",
        json={"token": admin_authorization, "password": "AnotherAdminPassword123!"},
    ).status_code == 400

    assert client.post(
        "/api/auth/login",
        json={"email": accounts["admin_email"], "password": accounts["old_password"]},
    ).status_code == 401
    assert client.post(
        "/api/auth/login",
        json={"email": accounts["admin_email"], "password": "NewAdminPassword123!"},
    ).status_code == 200
    assert client.post(
        "/api/customer-auth/login",
        json={"email": accounts["customer_email"], "password": accounts["old_password"]},
    ).status_code == 401
    assert client.post(
        "/api/customer-auth/login",
        json={"email": accounts["customer_email"], "password": "NewCustomerPassword123!"},
    ).status_code == 200

    with app.app_context():
        from app.extensions import db

        assert db.session.execute(
            text("SELECT id::text FROM users WHERE id = :id"),
            {"id": accounts["admin_id"]},
        ).scalar_one() == accounts["admin_id"]
        assert db.session.execute(
            text("SELECT id::text FROM customers WHERE id = :id"),
            {"id": accounts["customer_id"]},
        ).scalar_one() == accounts["customer_id"]


def test_unknown_account_response_does_not_confirm_email_delivery(
        client, app, monkeypatch
):
        from app.utils import password_reset

        monkeypatch.setitem(app.config, "MAIL_SERVER", "smtp.test")
        monkeypatch.setitem(app.config, "MAIL_PORT", 587)
        monkeypatch.setitem(app.config, "MAIL_USERNAME", "noreply@example.com")
        monkeypatch.setitem(app.config, "MAIL_PASSWORD", "test-app-password")
        monkeypatch.setitem(app.config, "MAIL_DEFAULT_SENDER", "noreply@example.com")
        monkeypatch.setitem(app.config, "MAIL_USE_TLS", True)
        monkeypatch.setitem(app.config, "MAIL_USE_SSL", False)
        monkeypatch.setattr(
            password_reset,
            "_send_otp_email",
            lambda *args: pytest.fail("No email should be sent for an unknown account."),
        )

        response = client.post(
            "/api/auth/forgot-password",
            json={"email": f"missing-{uuid.uuid4()}@example.com"},
        )

        assert response.status_code == 202
        assert response.get_json()["email_sent"] is False


def test_expired_and_exhausted_otps_are_rejected(
    client, app, reset_accounts, monkeypatch
):
    from app.extensions import db
    from app.utils import password_reset

    codes = []
    monkeypatch.setattr(
        password_reset,
        "_send_otp_email",
        lambda email, otp, account_type: codes.append(otp),
    )
    monkeypatch.setitem(app.config, "MAIL_SERVER", "smtp.test")
    monkeypatch.setitem(app.config, "MAIL_PORT", 587)
    monkeypatch.setitem(app.config, "MAIL_USERNAME", "noreply@example.com")
    monkeypatch.setitem(app.config, "MAIL_PASSWORD", "test-app-password")
    monkeypatch.setitem(app.config, "MAIL_DEFAULT_SENDER", "noreply@example.com")
    monkeypatch.setitem(app.config, "MAIL_USE_TLS", True)
    monkeypatch.setitem(app.config, "MAIL_USE_SSL", False)
    email = reset_accounts["admin_email"]

    assert client.post(
        "/api/auth/forgot-password",
        json={"email": email},
    ).status_code == 202
    with app.app_context():
        db.session.execute(
            text("""
                UPDATE password_reset_otps
                SET expires_at = NOW() - INTERVAL '1 second'
                WHERE user_id = :user_id
            """),
            {"user_id": reset_accounts["admin_id"]},
        )
        db.session.commit()
    assert client.post(
        "/api/auth/verify-otp",
        json={"email": email, "otp": codes[-1]},
    ).status_code == 400

    with app.app_context():
        db.session.execute(
            text("""
                UPDATE password_reset_otps
                SET created_at = NOW() - INTERVAL '61 seconds'
                WHERE user_id = :user_id
            """),
            {"user_id": reset_accounts["admin_id"]},
        )
        db.session.commit()
    assert client.post(
        "/api/auth/forgot-password",
        json={"email": email},
    ).status_code == 202
    wrong_code = f"{(int(codes[-1]) + 1) % 1_000_000:06d}"
    for _ in range(5):
        assert client.post(
            "/api/auth/verify-otp",
            json={"email": email, "otp": wrong_code},
        ).status_code == 400
    assert client.post(
        "/api/auth/verify-otp",
        json={"email": email, "otp": codes[-1]},
    ).status_code == 400
