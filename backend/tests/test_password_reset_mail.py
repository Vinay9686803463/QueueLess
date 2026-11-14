from flask import Flask

from app.utils import password_reset


def _mail_config(app):
    app.config.update(
        MAIL_SERVER="smtp.gmail.com",
        MAIL_PORT=587,
        MAIL_USE_TLS=True,
        MAIL_USE_SSL=False,
        MAIL_USERNAME="sender@example.com",
        MAIL_PASSWORD="test-app-password",
        MAIL_DEFAULT_SENDER="sender@example.com",
    )


def test_gmail_mail_configuration_is_recognized():
    app = Flask(__name__)
    _mail_config(app)

    with app.app_context():
        assert password_reset._email_is_configured()


def test_gmail_mail_configuration_requires_credentials_and_matching_sender():
    app = Flask(__name__)
    _mail_config(app)
    app.config["MAIL_PASSWORD"] = ""

    with app.app_context():
        assert not password_reset._email_is_configured()

    app.config["MAIL_PASSWORD"] = "test-app-password"
    app.config["MAIL_DEFAULT_SENDER"] = "different@example.com"
    with app.app_context():
        assert not password_reset._email_is_configured()


def test_gmail_smtp_sender_uses_tls_auth_and_sends_message(monkeypatch):
    app = Flask(__name__)
    _mail_config(app)
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def starttls(self):
            calls.append(("starttls",))

        def login(self, username, password):
            calls.append(("login", username, password))

        def send_message(self, message):
            calls.append(("send", message["To"], message["From"], message.get_content()))

    monkeypatch.setattr(password_reset.smtplib, "SMTP", FakeSMTP)

    with app.app_context():
        password_reset._send_otp_email(
            "customer@example.com",
            "123456",
            "customer",
        )

    assert calls[0] == ("connect", "smtp.gmail.com", 587, 10)
    assert calls[1] == ("starttls",)
    assert calls[2] == ("login", "sender@example.com", "test-app-password")
    assert calls[3][0:3] == (
        "send",
        "customer@example.com",
        "sender@example.com",
    )
    assert "123456" in calls[3][3]


def test_gmail_smtp_sender_raises_when_recipient_is_refused(monkeypatch):
    app = Flask(__name__)
    _mail_config(app)

    class RefusingSMTP:
        def __init__(self, host, port, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def ehlo(self):
            return 250, b"ok"

        def starttls(self):
            return 220, b"ready"

        def login(self, username, password):
            return 235, b"authenticated"

        def send_message(self, message):
            return {message["To"]: (550, b"recipient refused")}

    monkeypatch.setattr(password_reset.smtplib, "SMTP", RefusingSMTP)

    with app.app_context():
        try:
            password_reset._send_otp_email(
                "customer@example.com",
                "123456",
                "customer",
            )
        except password_reset.smtplib.SMTPRecipientsRefused as error:
            assert list(error.recipients.values())[0][0] == 550
        else:
            raise AssertionError("Recipient refusal should fail OTP email delivery.")
