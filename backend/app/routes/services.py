import uuid as uuid_lib

from flask import Blueprint, request, jsonify, g, current_app
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from .auth import token_required


service_bp = Blueprint(
    "services",
    __name__,
    url_prefix="/api/businesses"
)


def _is_uuid(value):
    try:
        uuid_lib.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def _accessible_business_ids(user_id):
    rows = db.session.execute(
        text("""
            SELECT id::text AS id
            FROM businesses
            WHERE owner_id = :user_id

            UNION

            SELECT business_id::text AS id
            FROM business_staff
            WHERE user_id = :user_id
              AND is_active = TRUE
        """),
        {"user_id": user_id},
    ).fetchall()
    return {row[0] for row in rows}


def get_service_columns():
    return """
        id::text AS id,
        business_id::text AS business_id,
        service_name,
        description,
        duration_minutes,
        price,
        is_active,
        created_at,
        updated_at
    """


def serialize_service(row):
    if row is None:
        return None
    service = dict(row)
    for field in ("created_at", "updated_at"):
        value = service.get(field)
        if value is not None and hasattr(value, "isoformat"):
            service[field] = value.isoformat()
    return service


def validate_service_data(data, creating=False):
    if not isinstance(data, dict):
        return "Request body must be a JSON object"

    if creating:
        if not str(data.get("service_name", "")).strip():
            return "Service name is required"

    if "service_name" in data:
        if not isinstance(data["service_name"], str):
            return "Service name must be text"
        if not data["service_name"].strip():
            return "Service name cannot be empty"
        if len(data["service_name"].strip()) > 120:
            return "Service name cannot exceed 120 characters"

    if "description" in data and data["description"] is not None:
        if not isinstance(data["description"], str):
            return "Description must be text"

    if "duration_minutes" in data:
        value = data["duration_minutes"]
        if isinstance(value, bool) or not isinstance(value, int):
            return "Duration must be a whole number"
        if value <= 0:
            return "Duration must be greater than zero"

    if "price" in data:
        value = data["price"]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return "Price must be a number"
        if value < 0:
            return "Price cannot be negative"

    if "is_active" in data and not isinstance(data["is_active"], bool):
        return "is_active must be true or false"

    return None


SERVICE_FIELDS = {
    "service_name",
    "description",
    "duration_minutes",
    "price",
    "is_active",
}


@service_bp.route("/<business_id>/services", methods=["POST"])
@token_required
def create_service(business_id):
    if not _is_uuid(business_id):
        return jsonify({"status": "error", "message": "Business not found"}), 404

    user_id = g.current_user["id"]
    if business_id not in _accessible_business_ids(user_id):
        return jsonify({"status": "error", "message": "Business not found"}), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "A valid JSON object is required"}), 400

    error = validate_service_data(data, creating=True)
    if error:
        return jsonify({"status": "error", "message": error}), 400

    try:
        result = db.session.execute(
            text("""
                INSERT INTO services (
                    business_id,
                    service_name,
                    description,
                    duration_minutes,
                    price,
                    is_active
                )
                VALUES (
                    :business_id,
                    :service_name,
                    :description,
                    :duration_minutes,
                    :price,
                    :is_active
                )
                RETURNING
            """ + get_service_columns()),
            {
                "business_id": business_id,
                "service_name": data["service_name"].strip(),
                "description": data.get("description"),
                "duration_minutes": data.get("duration_minutes", 15),
                "price": data.get("price", 0),
                "is_active": bool(data.get("is_active", True)),
            },
        ).mappings().first()

        db.session.commit()

        return jsonify({
            "status": "success",
            "message": "Service created successfully",
            "service": serialize_service(result),
        }), 201

    except IntegrityError:
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": "A service with this name already exists for this business",
        }), 409

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Service creation failed")
        return jsonify({"status": "error", "message": "Service creation failed. Please try again."}), 500


@service_bp.route("/<business_id>/services", methods=["GET"])
@token_required
def list_services(business_id):
    if not _is_uuid(business_id):
        return jsonify({"status": "error", "message": "Business not found"}), 404

    user_id = g.current_user["id"]
    if business_id not in _accessible_business_ids(user_id):
        return jsonify({"status": "error", "message": "Business not found"}), 404

    try:
        rows = db.session.execute(
            text("""
                SELECT
            """ + get_service_columns() + """
                FROM services
                WHERE business_id = :business_id
                ORDER BY created_at ASC
            """),
            {"business_id": business_id},
        ).mappings().all()

        return jsonify({
            "status": "success",
            "count": len(rows),
            "services": [serialize_service(row) for row in rows],
        }), 200

    except Exception:
        current_app.logger.exception("Service listing failed")
        return jsonify({"status": "error", "message": "Unable to retrieve services"}), 500


@service_bp.route("/<business_id>/services/<service_id>", methods=["GET"])
@token_required
def get_service(business_id, service_id):
    if not _is_uuid(business_id) or not _is_uuid(service_id):
        return jsonify({"status": "error", "message": "Service not found"}), 404

    user_id = g.current_user["id"]
    if business_id not in _accessible_business_ids(user_id):
        return jsonify({"status": "error", "message": "Business not found"}), 404

    try:
        service = db.session.execute(
            text("""
                SELECT
            """ + get_service_columns() + """
                FROM services
                WHERE id = :service_id
                  AND business_id = :business_id
            """),
            {"service_id": service_id, "business_id": business_id},
        ).mappings().first()

        if not service:
            return jsonify({"status": "error", "message": "Service not found"}), 404

        return jsonify({
            "status": "success",
            "service": serialize_service(service),
        }), 200

    except Exception:
        current_app.logger.exception("Service retrieval failed")
        return jsonify({"status": "error", "message": "Unable to retrieve service"}), 500


@service_bp.route("/<business_id>/services/<service_id>", methods=["PUT"])
@token_required
def update_service(business_id, service_id):
    if not _is_uuid(business_id) or not _is_uuid(service_id):
        return jsonify({"status": "error", "message": "Service not found"}), 404

    user_id = g.current_user["id"]
    if business_id not in _accessible_business_ids(user_id):
        return jsonify({"status": "error", "message": "Business not found"}), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return jsonify({"status": "error", "message": "Provide at least one field to update"}), 400

    error = validate_service_data(data)
    if error:
        return jsonify({"status": "error", "message": error}), 400

    updates = {key: value for key, value in data.items() if key in SERVICE_FIELDS}
    if not updates:
        return jsonify({"status": "error", "message": "No valid service fields provided"}), 400

    if "service_name" in updates and isinstance(updates["service_name"], str):
        updates["service_name"] = updates["service_name"].strip()

    if "description" in updates:
        updates["description"] = updates["description"].strip() if isinstance(updates["description"], str) else updates["description"]

    # Column names come only from the fixed allowlist above.
    set_clause = ", ".join(f"{field} = :{field}" for field in updates)

    try:
        updates["service_id"] = service_id
        updates["business_id"] = business_id

        service = db.session.execute(
            text(f"""
                UPDATE services
                SET {set_clause},
                    updated_at = NOW()
                WHERE id = :service_id
                  AND business_id = :business_id
                RETURNING
            """ + get_service_columns()),
            updates,
        ).mappings().first()

        if not service:
            db.session.rollback()
            return jsonify({"status": "error", "message": "Service not found"}), 404

        db.session.commit()

        return jsonify({
            "status": "success",
            "message": "Service updated successfully",
            "service": serialize_service(service),
        }), 200

    except IntegrityError:
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": "A service with this name already exists for this business",
        }), 409

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Service update failed")
        return jsonify({"status": "error", "message": "Service update failed. Please try again."}), 500


@service_bp.route("/<business_id>/services/<service_id>", methods=["DELETE"])
@token_required
def deactivate_service(business_id, service_id):
    if not _is_uuid(business_id) or not _is_uuid(service_id):
        return jsonify({"status": "error", "message": "Service not found"}), 404

    user_id = g.current_user["id"]
    if business_id not in _accessible_business_ids(user_id):
        return jsonify({"status": "error", "message": "Business not found"}), 404

    try:
        service = db.session.execute(
            text("""
                UPDATE services
                SET is_active = FALSE,
                    updated_at = NOW()
                WHERE id = :service_id
                  AND business_id = :business_id
                RETURNING
            """ + get_service_columns()),
            {"service_id": service_id, "business_id": business_id},
        ).mappings().first()

        if not service:
            db.session.rollback()
            return jsonify({"status": "error", "message": "Service not found"}), 404

        db.session.commit()

        return jsonify({
            "status": "success",
            "message": "Service deactivated successfully",
            "service": serialize_service(service),
        }), 200

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Service deactivation failed")
        return jsonify({"status": "error", "message": "Service deactivation failed. Please try again."}), 500