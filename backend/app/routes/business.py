import re
import uuid as uuid_lib
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


def _is_uuid(value):
    try:
        uuid_lib.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


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
        if len(data["business_name"].strip()) > 150:
            return "Business name cannot exceed 150 characters"

    if "business_type" in data:
        if not isinstance(data["business_type"], str):
            return "Business type must be text"
        if not data["business_type"].strip():
            return "Business type cannot be empty"
        if len(data["business_type"].strip()) > 80:
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
        if len(data["phone"].strip()) > 20:
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

        if value is None or isinstance(value, bool) or not isinstance(value, int):
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


def serialize_business(row):
    if row is None:
        return None

    business = dict(row)

    for field in ("opening_time", "closing_time"):
        value = business.get(field)
        if value is not None and hasattr(value, "strftime"):
            business[field] = value.strftime("%H:%M")

    return business


def _clean_text(value):
    if isinstance(value, str):
        return value.strip()
    return value


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
                "description": _clean_text(data.get("description")),
                "address": _clean_text(data.get("address")),
                "phone": _clean_text(data.get("phone")),
                "email": (
                    data.get("email").strip().lower()
                    if isinstance(data.get("email"), str) and data.get("email").strip()
                    else None
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
            "business": serialize_business(result)
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
            "businesses": [serialize_business(b) for b in businesses]
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
    if not _is_uuid(business_id):
        return jsonify({
            "status": "error",
            "message": "Business not found"
        }), 404

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
            "business": serialize_business(business)
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
    if not _is_uuid(business_id):
        return jsonify({
            "status": "error",
            "message": "Business not found"
        }), 404

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

    if "business_name" in updates and isinstance(updates["business_name"], str):
        updates["business_name"] = updates["business_name"].strip()

    if "business_type" in updates and isinstance(updates["business_type"], str):
        updates["business_type"] = updates["business_type"].strip()

    if "description" in updates:
        updates["description"] = _clean_text(updates["description"])

    if "address" in updates:
        updates["address"] = _clean_text(updates["address"])

    if "phone" in updates:
        updates["phone"] = _clean_text(updates["phone"])

    if "email" in updates:
        if isinstance(updates["email"], str) and updates["email"].strip():
            updates["email"] = updates["email"].strip().lower()
        else:
            updates["email"] = None

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
            "business": serialize_business(business)
        }), 200

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Business update failed")

        return jsonify({
            "status": "error",
            "message": "Business update failed. Please try again."
        }), 500
