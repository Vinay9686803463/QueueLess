cat > app/routes/business.py <<'PY'
import re
from datetime import datetime

from flask import Blueprint, request, jsonify, g, current_app
from sqlalchemy import text

from ..extensions import db
from .auth import token_required


business_bp = Blueprint(
    "business",
    __name__,
    url_prefix="/api/businesses"
)


def validate_business_data(data, creating=False):
    if not isinstance(data, dict):
        return "Request body must be a JSON object"

    if creating:
        if not str(data.get("business_name", "")).strip():
            return "Business name is required"

        if not str(data.get("business_type", "")).strip():
            return "Business type is required"

    if "business_name" in data:
        if not isinstance(data["business_name"], str):
            return "Business name must be text"
        if not data["business_name"].strip():
            return "Business name cannot be empty"
        if len(data["business_name"]) > 150:
            return "Business name cannot exceed 150 characters"

    if "business_type" in data:
        if not isinstance(data["business_type"], str):
            return "Business type must be text"
        if not data["business_type"].strip():
            return "Business type cannot be empty"
        if len(data["business_type"]) > 80:
            return "Business type cannot exceed 80 characters"

    if "description" in data and data["description"] is not None:
        if not isinstance(data["description"], str):
            return "Description must be text"

    if "address" in data and data["address"] is not None:
        if not isinstance(data["address"], str):
            return "Address must be text"

    if "phone" in data and data["phone"] is not None:
        if not isinstance(data["phone"], str):
            return "Phone must be text"
        if len(data["phone"]) > 20:
            return "Phone cannot exceed 20 characters"

    if "email" in data and data["email"] is not None:
        if not isinstance(data["email"], str):
            return "Email must be text"
        email = data["email"].strip()
        if email and (
            not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email)
            or len(email) > 255
        ):
            return "Enter a valid business email address"

    for field in ("opening_time", "closing_time"):
        if field in data and data[field] is not None:
            try:
                datetime.strptime(data[field], "%H:%M")
            except (ValueError, TypeError):
                return f"{field} must use HH:MM format"

    if "average_service_time" in data:
        value = data["average_service_time"]

        if isinstance(value, bool) or not isinstance(value, int):
            return "Average service time must be a whole number"

        if value <= 0:
            return "Average service time must be greater than zero"

    return None


BUSINESS_FIELDS = {
    "business_name",
    "business_type",
    "description",
    "address",
    "phone",
    "email",
    "opening_time",
    "closing_time",
    "average_service_time"
}


def get_business_columns():
    return """
        id::text AS id,
        owner_id::text AS owner_id,
        business_name,
        business_type,
        description,
        address,
        phone,
        email,
        opening_time,
        closing_time,
        average_service_time,
        is_active,
        created_at,
        updated_at
    """


@business_bp.route("", methods=["POST"])
@token_required
def create_business():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "status": "error",
            "message": "A valid JSON object is required"
        }), 400

    error = validate_business_data(data, creating=True)

    if error:
        return jsonify({
            "status": "error",
            "message": error
        }), 400

    try:
        result = db.session.execute(
            text("""
                INSERT INTO businesses (
                    owner_id,
                    business_name,
                    business_type,
                    description,
                    address,
                    phone,
                    email,
                    opening_time,
                    closing_time,
                    average_service_time
                )
                VALUES (
                    :owner_id,
                    :business_name,
                    :business_type,
                    :description,
                    :address,
                    :phone,
                    :email,
                    :opening_time,
                    :closing_time,
                    :average_service_time
                )
                RETURNING
            """ + get_business_columns()),
            {
                "owner_id": g.current_user["id"],
                "business_name": data["business_name"].strip(),
                "business_type": data["business_type"].strip(),
                "description": data.get("description"),
                "address": data.get("address"),
                "phone": data.get("phone"),
                "email": (
                    data.get("email", "").strip().lower()
                    if data.get("email") else None
                ),
                "opening_time": data.get("opening_time"),
                "closing_time": data.get("closing_time"),
                "average_service_time": data.get(
                    "average_service_time", 15
                )
            }
        ).mappings().first()

        db.session.commit()

        return jsonify({
            "status": "success",
            "message": "Business profile created successfully",
            "business": dict(result)
        }), 201

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Business creation failed")

        return jsonify({
            "status": "error",
            "message": "Business creation failed. Please try again."
        }), 500


@business_bp.route("", methods=["GET"])
@token_required
def get_my_businesses():
    try:
        businesses = db.session.execute(
            text("""
                SELECT
            """ + get_business_columns() + """
                FROM businesses
                WHERE owner_id = :owner_id
                ORDER BY created_at DESC
            """),
            {"owner_id": g.current_user["id"]}
        ).mappings().all()

        return jsonify({
            "status": "success",
            "count": len(businesses),
            "businesses": [dict(business) for business in businesses]
        }), 200

    except Exception:
        current_app.logger.exception("Business listing failed")

        return jsonify({
            "status": "error",
            "message": "Unable to retrieve businesses"
        }), 500


@business_bp.route("/<business_id>", methods=["GET"])
@token_required
def get_business(business_id):
    try:
        business = db.session.execute(
            text("""
                SELECT
            """ + get_business_columns() + """
                FROM businesses
                WHERE id = :business_id
                AND owner_id = :owner_id
            """),
            {
                "business_id": business_id,
                "owner_id": g.current_user["id"]
            }
        ).mappings().first()

        if not business:
            return jsonify({
                "status": "error",
                "message": "Business not found"
            }), 404

        return jsonify({
            "status": "success",
            "business": dict(business)
        }), 200

    except Exception:
        current_app.logger.exception("Business retrieval failed")

        return jsonify({
            "status": "error",
            "message": "Unable to retrieve business"
        }), 500


@business_bp.route("/<business_id>", methods=["PUT"])
@token_required
def update_business(business_id):
    data = request.get_json(silent=True)

    if not isinstance(data, dict) or not data:
        return jsonify({
            "status": "error",
            "message": "Provide at least one field to update"
        }), 400

    error = validate_business_data(data)

    if error:
        return jsonify({
            "status": "error",
            "message": error
        }), 400

    updates = {
        key: value
        for key, value in data.items()
        if key in BUSINESS_FIELDS
    }

    if not updates:
        return jsonify({
            "status": "error",
            "message": "No valid business fields provided"
        }), 400

    if "business_name" in updates:
        updates["business_name"] = updates["business_name"].strip()

    if "business_type" in updates:
        updates["business_type"] = updates["business_type"].strip()

    if "email" in updates and updates["email"]:
        updates["email"] = updates["email"].strip().lower()

    # Column names come only from the fixed allowlist above.
    set_clause = ", ".join(
        f"{field} = :{field}" for field in updates
    )

    try:
        updates["business_id"] = business_id
        updates["owner_id"] = g.current_user["id"]

        business = db.session.execute(
            text(f"""
                UPDATE businesses
                SET {set_clause},
                    updated_at = NOW()
                WHERE id = :business_id
                AND owner_id = :owner_id
                RETURNING
            """ + get_business_columns()),
            updates
        ).mappings().first()

        if not business:
            db.session.rollback()
            return jsonify({
                "status": "error",
                "message": "Business not found"
            }), 404

        db.session.commit()

        return jsonify({
            "status": "success",
            "message": "Business profile updated successfully",
            "business": dict(business)
        }), 200

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Business update failed")

        return jsonify({
            "status": "error",
            "message": "Business update failed. Please try again."
        }), 500
PY