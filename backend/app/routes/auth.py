import os
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt

from flask import (  # type: ignore[reportMissingImports]
    Blueprint,
    request,
    jsonify,
    current_app,
    g
)

from sqlalchemy import text  # type: ignore[reportMissingImports]
from sqlalchemy.exc import IntegrityError  # type: ignore[reportMissingImports]
from werkzeug.security import (  # type: ignore[reportMissingImports]
    generate_password_hash,
    check_password_hash
)

from ..extensions import db
from ..utils.rate_limit import rate_limiter


auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def generate_token(user_id):
    now = datetime.now(timezone.utc)

    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(
            seconds=current_app.config["JWT_ACCESS_TOKEN_EXPIRES"]
        )
    }

    return jwt.encode(
        payload,
        current_app.config["JWT_SECRET_KEY"],
        algorithm="HS256"
    )


def token_required(func):
    @wraps(func)
    def decorated(*args, **kwargs):

        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            return jsonify({
                "status": "error",
                "message": "Authentication token is required"
            }), 401

        token = auth_header.split(" ", 1)[1].strip()

        try:
            payload = jwt.decode(
                token,
                current_app.config["JWT_SECRET_KEY"],
                algorithms=["HS256"]
            )

            user = db.session.execute(
                text("""
                    SELECT
                        id::text AS id,
                        full_name,
                        email,
                        phone,
                        is_active
                    FROM users
                    WHERE id = :user_id
                """),
                {"user_id": payload["sub"]}
            ).mappings().first()

            if not user or not user["is_active"]:
                return jsonify({
                    "status": "error",
                    "message": "User account not found or inactive"
                }), 401

            g.current_user = dict(user)

        except jwt.ExpiredSignatureError:
            return jsonify({
                "status": "error",
                "message": "Token has expired. Please login again."
            }), 401

        except jwt.InvalidTokenError:
            return jsonify({
                "status": "error",
                "message": "Invalid authentication token"
            }), 401

        return func(*args, **kwargs)

    return decorated


@auth_bp.route("/register", methods=["POST"])
@rate_limiter.limit(5, 60)
def register():

    data = request.get_json(silent=True) or {}

    full_name = str(data.get("full_name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    phone = str(data.get("phone", "")).strip()
    password = data.get("password", "")

    if not full_name or not email or not password:
        return jsonify({
            "status": "error",
            "message": "Full name, email and password are required"
        }), 400

    if len(full_name) > 120 or len(email) > 255 or len(phone) > 20:
        return jsonify({
            "status": "error",
            "message": "One or more fields exceed the allowed length"
        }), 400

    if "@" not in email or email.startswith("@") or email.endswith("@"):
        return jsonify({
            "status": "error",
            "message": "Enter a valid email address"
        }), 400

    if not isinstance(password, str) or len(password) < 8:
        return jsonify({
            "status": "error",
            "message": "Password must contain at least 8 characters"
        }), 400

    if len(password) > 128:
        return jsonify({
            "status": "error",
            "message": "Password is too long"
        }), 400

    password_hash = generate_password_hash(password)

    try:
        result = db.session.execute(
            text("""
                INSERT INTO users (
                    full_name,
                    email,
                    phone,
                    password_hash
                )
                VALUES (
                    :full_name,
                    :email,
                    :phone,
                    :password_hash
                )
                RETURNING
                    id::text AS id,
                    full_name,
                    email,
                    phone,
                    is_active
            """),
            {
                "full_name": full_name,
                "email": email,
                "phone": phone or None,
                "password_hash": password_hash
            }
        ).mappings().first()

        db.session.commit()

        user = dict(result)

        token = generate_token(user["id"])

        return jsonify({
            "status": "success",
            "message": "Registration successful",
            "user": user,
            "access_token": token,
            "token_type": "Bearer"
        }), 201

    except IntegrityError:
        db.session.rollback()

        return jsonify({
            "status": "error",
            "message": "An account with this email already exists"
        }), 409

    except Exception:
        db.session.rollback()

        current_app.logger.exception("Registration failed")

        return jsonify({
            "status": "error",
            "message": "Registration failed. Please try again."
        }), 500


@auth_bp.route("/login", methods=["POST"])
@rate_limiter.limit(10, 60)
def login():

    data = request.get_json(silent=True) or {}

    email = str(data.get("email", "")).strip().lower()
    password = data.get("password", "")

    if not email or not isinstance(password, str) or not password:
        return jsonify({
            "status": "error",
            "message": "Email and password are required"
        }), 400

    try:
        user = db.session.execute(
            text("""
                SELECT
                    id::text AS id,
                    full_name,
                    email,
                    phone,
                    password_hash,
                    is_active
                FROM users
                WHERE email = :email
            """),
            {"email": email}
        ).mappings().first()

        if (
            not user
            or not user["is_active"]
            or not check_password_hash(
                user["password_hash"],
                password
            )
        ):
            return jsonify({
                "status": "error",
                "message": "Invalid email or password"
            }), 401

        token = generate_token(user["id"])

        return jsonify({
            "status": "success",
            "message": "Login successful",
            "user": {
                "id": user["id"],
                "full_name": user["full_name"],
                "email": user["email"],
                "phone": user["phone"],
                "is_active": user["is_active"]
            },
            "access_token": token,
            "token_type": "Bearer"
        }), 200

    except Exception:
        current_app.logger.exception("Login failed")

        return jsonify({
            "status": "error",
            "message": "Login failed. Please try again."
        }), 500


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()

    # Always return success to avoid email enumeration.
    response = {"status": "success", "message": "If the email exists, a reset link has been sent."}

    if not email:
        return jsonify(response), 200

    try:
        user = db.session.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": email},
        ).mappings().first()

        if user:
            import secrets, hashlib
            from datetime import timedelta
            raw_token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
            expires = datetime.now(timezone.utc) + timedelta(hours=1)

            db.session.execute(
                text("""
                    INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)
                    VALUES (:user_id, :token_hash, :expires_at)
                """),
                {"user_id": user["id"], "token_hash": token_hash, "expires_at": expires},
            )
            db.session.commit()

            # Development-only: return token if email is not configured.
            if os.getenv("FLASK_ENV", "development").lower() != "production":
                response["reset_token"] = raw_token
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Forgot password failed")

    return jsonify(response), 200


@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json(silent=True) or {}
    token = data.get("token", "")
    new_password = data.get("password", "")

    if not token or not new_password:
        return jsonify({"status": "error", "message": "Token and new password are required."}), 400

    if len(new_password) < 8:
        return jsonify({"status": "error", "message": "Password must be at least 8 characters."}), 400

    import hashlib
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    try:
        row = db.session.execute(
            text("""
                SELECT id, user_id, expires_at, used_at
                FROM password_reset_tokens
                WHERE token_hash = :token_hash
            """),
            {"token_hash": token_hash},
        ).mappings().first()

        if not row or row["used_at"] is not None:
            return jsonify({"status": "error", "message": "Invalid or expired reset token."}), 400

        if row["expires_at"] < datetime.now(timezone.utc):
            return jsonify({"status": "error", "message": "Reset token has expired."}), 400

        new_hash = generate_password_hash(new_password)
        db.session.execute(
            text("UPDATE users SET password_hash = :h WHERE id = :id"),
            {"h": new_hash, "id": row["user_id"]},
        )
        db.session.execute(
            text("UPDATE password_reset_tokens SET used_at = NOW() WHERE id = :id"),
            {"id": row["id"]},
        )
        db.session.commit()

        return jsonify({"status": "success", "message": "Password reset successful."}), 200
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Reset password failed")
        return jsonify({"status": "error", "message": "Password reset failed."}), 500


@auth_bp.route("/me", methods=["GET"])
@token_required
def get_current_user():

    return jsonify({
        "status": "success",
        "user": g.current_user
    }), 200