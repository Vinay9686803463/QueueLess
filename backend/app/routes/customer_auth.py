import jwt
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify, g, current_app
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
from ..extensions import db
from ..utils.password_reset import reset_password as reset_password_for_account
from ..utils.password_reset import send_otp, verify_otp
from ..utils.rate_limit import rate_limiter

customer_auth_bp = Blueprint("customer_auth", __name__, url_prefix="/api/customer-auth")

def _jwt_secret():
    return current_app.config["JWT_SECRET_KEY"]

def create_customer_token(customer_id):
    now = datetime.now(timezone.utc)
    payload = {"sub": str(customer_id), "role": "customer", "iat": now, "exp": now + timedelta(hours=24)}
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")

def decode_customer_token(token):
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
        if payload.get("role") != "customer":
            return None
        return payload.get("sub")
    except Exception:
        return None

def customer_token_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"status": "error", "message": "Authentication required."}), 401
        token = auth.split(" ", 1)[1].strip()
        try:
            payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
            if payload.get("role") != "customer":
                return jsonify({"status": "error", "message": "Invalid token."}), 401
            g.customer_id = payload["sub"]
        except Exception:
            return jsonify({"status": "error", "message": "Invalid or expired token."}), 401
        return func(*args, **kwargs)
    return wrapper


@customer_auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "A valid JSON object is required."}), 400

    full_name = data.get("full_name")
    email = data.get("email")
    phone = data.get("phone", "")
    password = data.get("password")

    if not isinstance(full_name, str) or not full_name.strip():
        return jsonify({"status": "error", "message": "Full name is required."}), 400
    if not isinstance(email, str) or not email.strip():
        return jsonify({"status": "error", "message": "Email is required."}), 400
    if not isinstance(password, str) or not password:
        return jsonify({"status": "error", "message": "Full name, email and password are required."}), 400
    if not isinstance(phone, str):
        return jsonify({"status": "error", "message": "Phone must be text."}), 400

    full_name = full_name.strip()
    email = email.strip().lower()
    phone = phone.strip()

    if len(full_name) > 120 or len(email) > 255 or len(phone) > 20:
        return jsonify({"status": "error", "message": "One or more fields exceed the allowed length."}), 400
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        return jsonify({"status": "error", "message": "Enter a valid email address."}), 400
    if len(password) < 8:
        return jsonify({"status": "error", "message": "Password must be at least 8 characters."}), 400
    if len(password) > 128:
        return jsonify({"status": "error", "message": "Password is too long."}), 400

    try:
        result = db.session.execute(
            text("""
                INSERT INTO customers (full_name, email, phone, password_hash)
                VALUES (:full_name, :email, :phone, :password_hash)
                RETURNING id::text AS id, full_name, email, phone, is_active
            """),
            {"full_name": full_name, "email": email, "phone": phone or None, "password_hash": generate_password_hash(password)},
        ).mappings().first()
        db.session.commit()
        return jsonify({"status": "success", "message": "Registration successful.", "access_token": create_customer_token(result["id"]), "customer": dict(result)}), 201
    except IntegrityError:
        db.session.rollback()
        return jsonify({"status": "error", "message": "An account with this email already exists."}), 409
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Customer registration failed")
        return jsonify({"status": "error", "message": "Registration failed."}), 500


@customer_auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "A valid JSON object is required."}), 400

    email = data.get("email")
    password = data.get("password")
    if not isinstance(email, str) or not email.strip() or not isinstance(password, str) or not password:
        return jsonify({"status": "error", "message": "Email and password are required."}), 400
    email = email.strip().lower()
    try:
        user = db.session.execute(
            text("SELECT id::text AS id, full_name, email, phone, password_hash, is_active FROM customers WHERE email = :email"),
            {"email": email},
        ).mappings().first()
        if not user or not user["is_active"] or not check_password_hash(user["password_hash"], password):
            return jsonify({"status": "error", "message": "Invalid email or password."}), 401
        return jsonify({"status": "success", "message": "Login successful.", "access_token": create_customer_token(user["id"]), "customer": {
            "id": user["id"], "full_name": user["full_name"], "email": user["email"], "phone": user["phone"]
        }}), 200
    except Exception:
        current_app.logger.exception("Customer login failed")
        return jsonify({"status": "error", "message": "Login failed."}), 500


@customer_auth_bp.route("/forgot-password", methods=["POST"])
@rate_limiter.limit(5, 300)
def forgot_password():
    data = request.get_json(silent=True) or {}
    return send_otp("customer", data.get("email"))


@customer_auth_bp.route("/verify-otp", methods=["POST"])
@rate_limiter.limit(15, 300)
def verify_password_reset_otp():
    data = request.get_json(silent=True) or {}
    return verify_otp("customer", data.get("email"), data.get("otp"))


@customer_auth_bp.route("/reset-password", methods=["POST"])
@rate_limiter.limit(10, 300)
def reset_password():
    data = request.get_json(silent=True) or {}
    return reset_password_for_account(
        "customer",
        data.get("token"),
        data.get("password"),
    )


@customer_auth_bp.route("/me", methods=["GET"])
@customer_token_required
def me():
    row = db.session.execute(
        text("SELECT id::text AS id, full_name, email, phone FROM customers WHERE id = :id"),
        {"id": g.customer_id},
    ).mappings().first()
    if not row:
        return jsonify({"status": "error", "message": "Customer not found."}), 404
    return jsonify({"status": "success", "customer": dict(row)}), 200


@customer_auth_bp.route("/appointments", methods=["GET"])
@customer_token_required
def my_appointments():
    rows = db.session.execute(
        text("""
            SELECT a.id::text AS id, a.customer_name, a.scheduled_at, a.status, s.service_name
            FROM appointments a
            LEFT JOIN services s ON s.id = a.service_id
            WHERE a.customer_id = :customer_id
            ORDER BY a.scheduled_at DESC
        """),
        {"customer_id": g.customer_id},
    ).mappings().all()
    return jsonify({"status": "success", "appointments": [dict(r) for r in rows]}), 200


@customer_auth_bp.route("/queue-tokens", methods=["GET"])
@customer_token_required
def my_tokens():
    rows = db.session.execute(
        text("""
            SELECT qt.id::text AS id, qt.token_number, qt.status, qt.tracking_code, qt.created_at, s.service_name,
                   (SELECT COUNT(*) FROM queue_tokens q2 WHERE q2.business_id = qt.business_id AND q2.queue_date = qt.queue_date AND q2.status = 'waiting' AND q2.token_number < qt.token_number) AS ahead
            FROM queue_tokens qt
            LEFT JOIN services s ON s.id = qt.service_id
            WHERE qt.customer_id = :customer_id
            ORDER BY qt.created_at DESC
        """),
        {"customer_id": g.customer_id},
    ).mappings().all()
    return jsonify({"status": "success", "tokens": [dict(r) for r in rows]}), 200