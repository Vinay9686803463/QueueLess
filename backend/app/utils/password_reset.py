import hashlib
import hmac
import secrets
import smtplib
from email.message import EmailMessage

from flask import current_app, jsonify
from sqlalchemy import text
from werkzeug.security import generate_password_hash

from ..extensions import db

OTP_LIFETIME_MINUTES = 5
OTP_RESEND_SECONDS = 60
OTP_MAX_ATTEMPTS = 5
RESET_LIFETIME_MINUTES = 10
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128

_ACCOUNT_TABLES = {
    "admin": ("users", "user_id"),
    "customer": ("customers", "customer_id"),
}


def _account_table(account_type):
    try:
        return _ACCOUNT_TABLES[account_type]
    except KeyError as error:
        raise ValueError("Unsupported account type.") from error


def _otp_digest(account_type, email, otp):
    secret = current_app.config["SECRET_KEY"].encode()
    value = f"{account_type}:{email}:{otp}".encode()
    return hmac.new(secret, value, hashlib.sha256).hexdigest()


def _token_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _email_is_configured():
    try:
        port = int(current_app.config.get("MAIL_PORT", 0))
    except (TypeError, ValueError):
        return False

    return bool(
        current_app.config.get("MAIL_SERVER")
        and current_app.config.get("MAIL_DEFAULT_SENDER")
        and port == current_app.config.get("MAIL_PORT")
        and 1 <= port <= 65535
        and not (
            current_app.config.get("MAIL_USE_SSL")
            and current_app.config.get("MAIL_USE_TLS")
        )
        and current_app.config.get("MAIL_USERNAME")
        and current_app.config.get("MAIL_PASSWORD")
        and current_app.config["MAIL_USERNAME"].strip().lower()
        == current_app.config["MAIL_DEFAULT_SENDER"].strip().lower()
    )


def _send_otp_email(email, otp, account_type):
    if not _email_is_configured():
        raise RuntimeError("Password reset email is not configured.")

    message = EmailMessage()
    message["Subject"] = "Your QueueLess password reset code"
    message["From"] = current_app.config["MAIL_DEFAULT_SENDER"]
    message["To"] = email
    message.set_content(
        f"Your QueueLess {account_type} password reset code is {otp}.\n\n"
        f"It expires in {OTP_LIFETIME_MINUTES} minutes. "
        "If you did not request this, you can ignore this email."
    )

    host = current_app.config["MAIL_SERVER"]
    port = current_app.config["MAIL_PORT"]
    username = current_app.config.get("MAIL_USERNAME")
    password = current_app.config.get("MAIL_PASSWORD")

    if current_app.config.get("MAIL_USE_SSL"):
        smtp_class = smtplib.SMTP_SSL
    else:
        smtp_class = smtplib.SMTP

    with smtp_class(host, port, timeout=10) as smtp:
        smtp.ehlo()
        current_app.logger.info(
            "Password reset SMTP connection established (portal=%s, server=%s, port=%s).",
            account_type,
            host,
            port,
        )
        if (
            not current_app.config.get("MAIL_USE_SSL")
            and current_app.config.get("MAIL_USE_TLS")
        ):
            smtp.starttls()
            smtp.ehlo()
            current_app.logger.info(
                "Password reset SMTP TLS enabled (portal=%s).",
                account_type,
            )
        if username and password:
            smtp.login(username, password)
            current_app.logger.info(
                "Password reset SMTP authentication succeeded (portal=%s).",
                account_type,
            )
        refused = smtp.send_message(message)
        if refused:
            response_codes = sorted({
                str(response[0])
                for response in refused.values()
                if isinstance(response, tuple) and response
            })
            current_app.logger.warning(
                "Password reset SMTP recipient rejected (portal=%s, response_codes=%s).",
                account_type,
                ",".join(response_codes) or "unknown",
            )
            raise smtplib.SMTPRecipientsRefused(refused)
        current_app.logger.info(
            "Password reset email accepted by SMTP server (portal=%s).",
            account_type,
        )


def _error(message, status):
    return jsonify({"status": "error", "message": message}), status


def send_otp(account_type, email):
    account_table, account_column = _account_table(account_type)
    if (
        not isinstance(email, str)
        or not email.strip()
        or len(email) > 255
        or email.count("@") != 1
        or any(character.isspace() for character in email)
    ):
        return _error("Enter a valid email address.", 400)
    email = email.strip().lower()
    generic_response = {
        "status": "success",
        "message": "If the email matches an active account in this portal, a verification code will be sent.",
    }

    try:
        if not _email_is_configured():
            return _error(
                "Password reset email is not configured. Contact the system administrator.",
                503,
            )

        account = db.session.execute(
            text(f"SELECT id FROM {account_table} WHERE email = :email AND is_active = TRUE"),
            {"email": email},
        ).mappings().first()
        if not account:
            current_app.logger.info(
                "Password reset request has no active account in portal=%s.",
                account_type,
            )
            return jsonify(generic_response), 202

        db.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": f"{account_type}:{account['id']}"},
        )
        latest = db.session.execute(
            text(f"""
                SELECT created_at
                FROM password_reset_otps
                WHERE {account_column} = :account_id
                ORDER BY created_at DESC
                LIMIT 1
                FOR UPDATE
            """),
            {"account_id": account["id"]},
        ).mappings().first()
        if latest:
            remaining = db.session.execute(
                text("""
                    SELECT GREATEST(
                        0,
                        CEIL(:cooldown - EXTRACT(EPOCH FROM (NOW() - :created_at)))
                    )::integer
                """),
                {
                    "cooldown": OTP_RESEND_SECONDS,
                    "created_at": latest["created_at"],
                },
            ).scalar() or 0
            if remaining > 0:
                db.session.rollback()
                response, status = _error(
                    "Please wait before requesting another verification code.",
                    429,
                )
                response.headers["Retry-After"] = str(remaining)
                return response, status

        db.session.execute(
            text(f"""
                UPDATE password_reset_otps
                SET used_at = COALESCE(used_at, NOW()),
                    reset_used_at = COALESCE(reset_used_at, NOW())
                WHERE {account_column} = :account_id
            """),
            {"account_id": account["id"]},
        )
        otp = f"{secrets.randbelow(1_000_000):06d}"
        challenge = db.session.execute(
            text(f"""
                INSERT INTO password_reset_otps (
                    {account_column}, email, otp_hash, expires_at
                )
                VALUES (
                    :account_id, :email, :otp_hash,
                    NOW() + (:lifetime * INTERVAL '1 minute')
                )
                RETURNING id
            """),
            {
                "account_id": account["id"],
                "email": email,
                "otp_hash": _otp_digest(account_type, email, otp),
                "lifetime": OTP_LIFETIME_MINUTES,
            },
        )
        db.session.commit()

        try:
            current_app.logger.info(
                "Password reset OTP email delivery started (portal=%s).",
                account_type,
            )
            _send_otp_email(email, otp, account_type)
        except smtplib.SMTPAuthenticationError as error:
            current_app.logger.error(
                "Password reset SMTP authentication failed (portal=%s, smtp_code=%s).",
                account_type,
                error.smtp_code,
            )
            db.session.execute(
                text("DELETE FROM password_reset_otps WHERE id = :id"),
                {"id": challenge["id"]},
            )
            db.session.commit()
            return _error(
                "Gmail rejected the SMTP credentials. Check MAIL_USERNAME and MAIL_PASSWORD in backend/.env; use a Gmail App Password.",
                503,
            )
        except smtplib.SMTPRecipientsRefused as error:
            response_codes = sorted({
                str(response[0])
                for response in error.recipients.values()
                if isinstance(response, tuple) and response
            })
            current_app.logger.warning(
                "Password reset SMTP refused recipient (portal=%s, response_codes=%s).",
                account_type,
                ",".join(response_codes) or "unknown",
            )
            db.session.execute(
                text("DELETE FROM password_reset_otps WHERE id = :id"),
                {"id": challenge["id"]},
            )
            db.session.commit()
            return _error(
                "Gmail did not accept the recipient address. Check the account email and try again.",
                503,
            )
        except (
            smtplib.SMTPConnectError,
            smtplib.SMTPServerDisconnected,
            TimeoutError,
            OSError,
        ) as error:
            current_app.logger.error(
                "Password reset SMTP connection failed (portal=%s, error_type=%s, smtp_code=%s).",
                account_type,
                type(error).__name__,
                getattr(error, "smtp_code", "none"),
            )
            db.session.execute(
                text("DELETE FROM password_reset_otps WHERE id = :id"),
                {"id": challenge["id"]},
            )
            db.session.commit()
            return _error(
                "Could not connect to Gmail SMTP. Check MAIL_SERVER, MAIL_PORT, TLS settings, and network access.",
                503,
            )
        except smtplib.SMTPResponseException as error:
            current_app.logger.error(
                "Password reset SMTP delivery failed (portal=%s, error_type=%s, smtp_code=%s).",
                account_type,
                type(error).__name__,
                error.smtp_code,
            )
            db.session.execute(
                text("DELETE FROM password_reset_otps WHERE id = :id"),
                {"id": challenge["id"]},
            )
            db.session.commit()
            return _error(
                "Gmail could not deliver the verification email. Check the sender settings and try again.",
                503,
            )
        except Exception as error:
            current_app.logger.error(
                "Password reset email delivery failed for %s account (%s).",
                account_type,
                type(error).__name__,
            )
            db.session.execute(
                text("DELETE FROM password_reset_otps WHERE id = :id"),
                {"id": challenge["id"]},
            )
            db.session.commit()
            return _error(
                "We could not deliver the verification email. Check Gmail SMTP settings and try again.",
                503,
            )

        return jsonify(generic_response), 202
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Password reset OTP request failed for %s account.", account_type)
        return _error("Unable to start password reset. Please try again later.", 500)


def verify_otp(account_type, email, otp):
    account_table, account_column = _account_table(account_type)
    if (
        not isinstance(email, str)
        or not email.strip()
        or not isinstance(otp, str)
        or len(otp) != 6
        or not otp.isdigit()
    ):
        return _error("Enter the email address and six-digit verification code.", 400)
    email = email.strip().lower()

    try:
        row = db.session.execute(
            text(f"""
                SELECT r.id, r.{account_column} AS account_id,
                       r.otp_hash, r.attempt_count
                FROM password_reset_otps r
                JOIN {account_table} a ON a.id = r.{account_column}
                WHERE r.email = :email
                  AND a.email = :email
                  AND a.is_active = TRUE
                  AND r.used_at IS NULL
                  AND r.expires_at > NOW()
                  AND r.attempt_count < :max_attempts
                ORDER BY r.created_at DESC
                LIMIT 1
                FOR UPDATE OF r
            """),
            {"email": email, "max_attempts": OTP_MAX_ATTEMPTS},
        ).mappings().first()
        if not row:
            db.session.rollback()
            return _error("Invalid or expired verification code.", 400)

        is_valid = hmac.compare_digest(
            row["otp_hash"],
            _otp_digest(account_type, email, otp),
        )
        if not is_valid:
            next_attempt_count = row["attempt_count"] + 1
            db.session.execute(
                text("""
                    UPDATE password_reset_otps
                    SET attempt_count = :attempt_count,
                        used_at = CASE WHEN :attempt_count >= :max_attempts THEN NOW() ELSE used_at END
                    WHERE id = :id
                """),
                {
                    "attempt_count": next_attempt_count,
                    "max_attempts": OTP_MAX_ATTEMPTS,
                    "id": row["id"],
                },
            )
            db.session.commit()
            return _error("Invalid or expired verification code.", 400)

        reset_token = secrets.token_urlsafe(32)
        db.session.execute(
            text("""
                UPDATE password_reset_otps
                SET used_at = NOW(),
                    verified_at = NOW(),
                    reset_token_hash = :reset_token_hash,
                    reset_expires_at = NOW() + (:lifetime * INTERVAL '1 minute')
                WHERE id = :id
            """),
            {
                "reset_token_hash": _token_digest(reset_token),
                "lifetime": RESET_LIFETIME_MINUTES,
                "id": row["id"],
            },
        )
        db.session.commit()
        return jsonify({
            "status": "success",
            "message": "Verification successful.",
            "reset_token": reset_token,
        }), 200
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Password reset OTP verification failed for %s account.", account_type)
        return _error("Unable to verify the code. Please try again later.", 500)


def reset_password(account_type, reset_token, new_password):
    account_table, account_column = _account_table(account_type)
    if not isinstance(reset_token, str) or not reset_token or len(reset_token) > 256:
        return _error("Invalid or expired password reset authorization.", 400)
    if not isinstance(new_password, str) or not new_password:
        return _error("New password is required.", 400)
    if len(new_password) < PASSWORD_MIN_LENGTH:
        return _error("Password must be at least 8 characters.", 400)
    if len(new_password) > PASSWORD_MAX_LENGTH:
        return _error("Password is too long.", 400)

    try:
        row = db.session.execute(
            text(f"""
                SELECT id, {account_column} AS account_id
                FROM password_reset_otps
                WHERE reset_token_hash = :token_hash
                  AND {account_column} IS NOT NULL
                  AND reset_used_at IS NULL
                  AND reset_expires_at > NOW()
                FOR UPDATE
            """),
            {"token_hash": _token_digest(reset_token)},
        ).mappings().first()
        if not row:
            db.session.rollback()
            return _error("Invalid or expired password reset authorization.", 400)

        db.session.execute(
            text(f"UPDATE {account_table} SET password_hash = :password_hash WHERE id = :account_id"),
            {
                "password_hash": generate_password_hash(new_password),
                "account_id": row["account_id"],
            },
        )
        db.session.execute(
            text(f"""
                UPDATE password_reset_otps
                SET reset_used_at = NOW(),
                    used_at = COALESCE(used_at, NOW())
                WHERE {account_column} = :account_id
            """),
            {"account_id": row["account_id"]},
        )
        db.session.commit()
        return jsonify({
            "status": "success",
            "message": "Password changed successfully.",
        }), 200
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Password reset failed for %s account.", account_type)
        return _error("Password reset failed. Please try again later.", 500)
