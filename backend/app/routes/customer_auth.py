from flask import Blueprint, request, jsonify, g, current_app
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
from ..extensions import db

customer_auth_bp = Blueprint("customer_auth", __name__, url_prefix="/api/customer-auth")


@customer_auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    full_name = str(data.get("full_name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    phone = str(data.get("phone", "")).strip()
    password = data.get("password", "")

    if not full_name or not email or not password:
        return jsonify({"status": "error", "message": "Full name, email and password are required."}), 400
    if len(password) < 8:
        return jsonify({"status": "error", "message": "Password must be at least 8 characters."}), 400

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
        return jsonify({"status": "success", "message": "Registration successful.", "customer": dict(result)}), 201
    except IntegrityError:
        db.session.rollback()
        return jsonify({"status": "error", "message": "An account with this email already exists."}), 409
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Customer registration failed")
        return jsonify({"status": "error", "message": "Registration failed."}), 500


@customer_auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = data.get("password", "")
    if not email or not password:
        return jsonify({"status": "error", "message": "Email and password are required."}), 400
    try:
        user = db.session.execute(
            text("SELECT id::text AS id, full_name, email, phone, password_hash, is_active FROM customers WHERE email = :email"),
            {"email": email},
        ).mappings().first()
        if not user or not user["is_active"] or not check_password_hash(user["password_hash"], password):
            return jsonify({"status": "error", "message": "Invalid email or password."}), 401
        return jsonify({"status": "success", "message": "Login successful.", "customer": {
            "id": user["id"], "full_name": user["full_name"], "email": user["email"], "phone": user["phone"]
        }}), 200
    except Exception:
        current_app.logger.exception("Customer login failed")
        return jsonify({"status": "error", "message": "Login failed."}), 500