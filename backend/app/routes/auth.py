import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt

from flask import (
    Blueprint,
    request,
    jsonify,
    current_app,
    g
)

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from ..extensions import db


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


@auth_bp.route("/me", methods=["GET"])
@token_required
def get_current_user():

    return jsonify({
        "status": "success",
        "user": g.current_user
    }), 200