import uuid as uuid_lib
from datetime import datetime, timezone, timedelta

from flask import Blueprint, request, jsonify, g, current_app
from sqlalchemy import text

from ..extensions import db
from .auth import token_required


appointment_bp = Blueprint(
    "appointments",
    __name__,
    url_prefix="/api/appointments",
)

ALLOWED_STATUSES = {
    "booked",
    "confirmed",
    "checked_in",
    "completed",
    "cancelled",
    "no_show",
}

APPOINTMENT_FIELDS = {
    "scheduled_at",
    "service_id",
    "customer_name",
    "customer_phone",
    "customer_email",
    "customer_id",
    "notes",
    "status",
}


def _is_uuid(value):
    try:
        uuid_lib.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def get_appointment_columns():
    return """
        id::text AS id,
        business_id::text AS business_id,
        service_id::text AS service_id,
        customer_name,
        customer_phone,
        customer_email,
        customer_id::text AS customer_id,
        scheduled_at,
        status,
        notes,
        created_at,
        updated_at
    """


def serialize_appointment(row):
    if row is None:
        return None

    appointment = dict(row)

    for field in ("scheduled_at", "created_at", "updated_at"):
        value = appointment.get(field)
        if value is not None and hasattr(value, "isoformat"):
            appointment[field] = value.isoformat()

    return appointment


def parse_datetime(value):
    if not isinstance(value, str):
        return None

    value = value.strip()

    if value.endswith("Z") or value.endswith("z"):
        value = value[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def accessible_business_ids(user_id):
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


def validate_customer_fields(data, creating=False):
    if not isinstance(data, dict):
        return "Request body must be a JSON object"

    if creating:
        if not str(data.get("customer_name", "")).strip():
            return "Customer name is required"
        if not str(data.get("customer_phone", "")).strip():
            return "Customer phone is required"

    if "customer_name" in data:
        if not isinstance(data["customer_name"], str):
            return "Customer name must be text"
        if not data["customer_name"].strip():
            return "Customer name cannot be empty"
        if len(data["customer_name"].strip()) > 120:
            return "Customer name cannot exceed 120 characters"

    if "customer_phone" in data:
        if not isinstance(data["customer_phone"], str):
            return "Customer phone must be text"
        if not data["customer_phone"].strip():
            return "Customer phone cannot be empty"
        if len(data["customer_phone"].strip()) > 20:
            return "Customer phone cannot exceed 20 characters"

    if "customer_email" in data and data["customer_email"] is not None:
        if not isinstance(data["customer_email"], str):
            return "Customer email must be text"
        email = data["customer_email"].strip()
        if email and (
            "@" not in email
            or email.startswith("@")
            or email.endswith("@")
            or len(email) > 255
        ):
            return "Enter a valid customer email address"

    if "notes" in data and data["notes"] is not None:
        if not isinstance(data["notes"], str):
            return "Notes must be text"

    if "status" in data:
        if data["status"] not in ALLOWED_STATUSES:
            return "Invalid appointment status"

    return None


def check_booking_conflict(business_id, service_id, scheduled_at, duration_minutes, exclude_appointment_id=None):
    rows = db.session.execute(
        text("""
            SELECT
                a.id::text AS id,
                a.scheduled_at,
                s.duration_minutes
            FROM appointments a
            JOIN services s ON s.id = a.service_id
            WHERE a.business_id = :business_id
              AND a.status NOT IN ('cancelled', 'no_show')
              AND (:exclude_id IS NULL OR a.id <> :exclude_id)
        """),
        {
            "business_id": business_id,
            "exclude_id": exclude_appointment_id,
        },
    ).mappings().all()

    new_start = scheduled_at
    new_end = scheduled_at + timedelta(minutes=duration_minutes)

    for row in rows:
        existing_start = row["scheduled_at"]

        if existing_start.tzinfo is None:
            existing_start = existing_start.replace(tzinfo=timezone.utc)
        else:
            existing_start = existing_start.astimezone(timezone.utc)

        existing_end = existing_start + timedelta(minutes=row["duration_minutes"])

        if existing_start < new_end and new_start < existing_end:
            return True

    return False


def validate_business_hours(business, scheduled_at, duration_minutes):
    opening = business.get("opening_time")
    closing = business.get("closing_time")

    if opening is None and closing is None:
        return None

    local_dt = scheduled_at.astimezone(timezone.utc)
    start_time = local_dt.timetz().replace(tzinfo=None) if False else local_dt.time()
    end_dt = local_dt + timedelta(minutes=duration_minutes)
    end_time = end_dt.time()

    if opening is not None and closing is not None:
        if opening < closing:
            if not (start_time >= opening and end_time <= closing):
                return "Appointment is outside business hours"
        else:
            # Overnight business hours.
            if not (start_time >= opening or end_time <= closing):
                return "Appointment is outside business hours"
    elif opening is not None:
        if start_time < opening:
            return "Appointment is outside business hours"
    elif closing is not None:
        if end_time > closing:
            return "Appointment is outside business hours"

    return None


@appointment_bp.route("", methods=["POST"])
@token_required
def create_appointment():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "status": "error",
            "message": "A valid JSON object is required",
        }), 400

    business_id = data.get("business_id")
    service_id = data.get("service_id")

    if not _is_uuid(business_id):
        return jsonify({"status": "error", "message": "Invalid business ID"}), 400

    if not _is_uuid(service_id):
        return jsonify({"status": "error", "message": "Invalid service ID"}), 400

    error = validate_customer_fields(data, creating=True)
    if error:
        return jsonify({"status": "error", "message": error}), 400

    scheduled_at = parse_datetime(data.get("scheduled_at"))
    if scheduled_at is None:
        return jsonify({
            "status": "error",
            "message": "Appointment date and time must use ISO 8601 format",
        }), 400

    if scheduled_at < datetime.now(timezone.utc):
        return jsonify({
            "status": "error",
            "message": "Appointments cannot be scheduled in the past",
        }), 400

    business_ids = accessible_business_ids(g.current_user["id"])
    if str(business_id) not in business_ids:
        return jsonify({"status": "error", "message": "Business not found"}), 404

    try:
        business = db.session.execute(
            text("""
                SELECT
                    id::text AS id,
                    opening_time,
                    closing_time,
                    is_active
                FROM businesses
                WHERE id = :business_id
            """),
            {"business_id": business_id},
        ).mappings().first()

        if not business or not business["is_active"]:
            return jsonify({"status": "error", "message": "Business not found"}), 404

        service = db.session.execute(
            text("""
                SELECT
                    id::text AS id,
                    business_id::text AS business_id,
                    duration_minutes,
                    is_active
                FROM services
                WHERE id = :service_id
            """),
            {"service_id": service_id},
        ).mappings().first()

        if (
            not service
            or not service["is_active"]
            or str(service["business_id"]) != str(business_id)
        ):
            return jsonify({"status": "error", "message": "Service not found"}), 404

        hours_error = validate_business_hours(
            business, scheduled_at, service["duration_minutes"]
        )
        if hours_error:
            return jsonify({"status": "error", "message": hours_error}), 400

        # Serialize access per business to reduce race conditions.
        db.session.execute(
            text("SELECT id FROM businesses WHERE id = :business_id FOR UPDATE"),
            {"business_id": business_id},
        )

        if check_booking_conflict(
            business_id,
            service_id,
            scheduled_at,
            service["duration_minutes"],
        ):
            return jsonify({
                "status": "error",
                "message": "This appointment conflicts with an existing appointment",
            }), 409

        result = db.session.execute(
            text("""
                INSERT INTO appointments (
                    business_id,
                    service_id,
                    customer_name,
                    customer_phone,
                    customer_email,
                    customer_id,
                    scheduled_at,
                    status,
                    notes
                )
                VALUES (
                    :business_id,
                    :service_id,
                    :customer_name,
                    :customer_phone,
                    :customer_email,
                    :customer_id,
                    :scheduled_at,
                    'booked',
                    :notes
                )
                RETURNING
            """ + get_appointment_columns()),
            {
                "business_id": business_id,
                "service_id": service_id,
                "customer_name": data["customer_name"].strip(),
                "customer_phone": data["customer_phone"].strip(),
                "customer_email": (
                    data["customer_email"].strip()
                    if isinstance(data.get("customer_email"), str)
                    and data["customer_email"].strip()
                    else None
                ),
                "customer_id": data.get("customer_id") if _is_uuid(data.get("customer_id")) else None,
                "scheduled_at": scheduled_at,
                "notes": (
                    data["notes"].strip()
                    if isinstance(data.get("notes"), str)
                    else None
                ),
            },
        ).mappings().first()

        db.session.commit()

        return jsonify({
            "status": "success",
            "message": "Appointment created successfully",
            "appointment": serialize_appointment(result),
        }), 201

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Appointment creation failed")

        return jsonify({
            "status": "error",
            "message": "Appointment creation failed. Please try again.",
        }), 500


@appointment_bp.route("/<appointment_id>", methods=["GET"])
@token_required
def get_appointment(appointment_id):
    if not _is_uuid(appointment_id):
        return jsonify({"status": "error", "message": "Appointment not found"}), 404

    business_ids = accessible_business_ids(g.current_user["id"])

    try:
        appointment = db.session.execute(
            text("""
                SELECT
            """ + get_appointment_columns() + """
                FROM appointments
                WHERE id = :appointment_id
            """),
            {"appointment_id": appointment_id},
        ).mappings().first()

        if not appointment or str(appointment["business_id"]) not in business_ids:
            return jsonify({"status": "error", "message": "Appointment not found"}), 404

        return jsonify({
            "status": "success",
            "appointment": serialize_appointment(appointment),
        }), 200

    except Exception:
        current_app.logger.exception("Appointment retrieval failed")

        return jsonify({
            "status": "error",
            "message": "Unable to retrieve appointment",
        }), 500


@appointment_bp.route("", methods=["GET"])
@token_required
def list_appointments():
    business_ids = accessible_business_ids(g.current_user["id"])

    if not business_ids:
        return jsonify({
            "status": "success",
            "count": 0,
            "appointments": [],
        }), 200

    params = {"business_ids": tuple(business_ids)}

    query = """
        SELECT
    """ + get_appointment_columns() + """
        FROM appointments
        WHERE business_id::text IN :business_ids
    """

    try:
        appointments = db.session.execute(
            text(query), params
        ).mappings().all()

        return jsonify({
            "status": "success",
            "count": len(appointments),
            "appointments": [
                serialize_appointment(appointment) for appointment in appointments
            ],
        }), 200

    except Exception:
        current_app.logger.exception("Appointment listing failed")

        return jsonify({
            "status": "error",
            "message": "Unable to retrieve appointments",
        }), 500


@appointment_bp.route("/<appointment_id>", methods=["PUT"])
@token_required
def update_appointment(appointment_id):
    if not _is_uuid(appointment_id):
        return jsonify({"status": "error", "message": "Appointment not found"}), 404

    data = request.get_json(silent=True)

    if not isinstance(data, dict) or not data:
        return jsonify({
            "status": "error",
            "message": "Provide at least one field to update",
        }), 400

    business_ids = accessible_business_ids(g.current_user["id"])

    try:
        existing = db.session.execute(
            text("""
                SELECT
            """ + get_appointment_columns() + """
                FROM appointments
                WHERE id = :appointment_id
            """),
            {"appointment_id": appointment_id},
        ).mappings().first()

        if not existing or str(existing["business_id"]) not in business_ids:
            return jsonify({"status": "error", "message": "Appointment not found"}), 404

        error = validate_customer_fields(data)
        if error:
            return jsonify({"status": "error", "message": error}), 400

        updates = {
            key: value
            for key, value in data.items()
            if key in APPOINTMENT_FIELDS
        }

        if not updates:
            return jsonify({
                "status": "error",
                "message": "No valid appointment fields provided",
            }), 400

        business_id = existing["business_id"]

        # Validate service if it is being changed.
        service = None
        if "service_id" in updates:
            if not _is_uuid(updates["service_id"]):
                return jsonify({"status": "error", "message": "Invalid service ID"}), 400

            service = db.session.execute(
                text("""
                    SELECT
                        id::text AS id,
                        business_id::text AS business_id,
                        duration_minutes,
                        is_active
                    FROM services
                    WHERE id = :service_id
                """),
                {"service_id": updates["service_id"]},
            ).mappings().first()

            if (
                not service
                or not service["is_active"]
                or str(service["business_id"]) != str(business_id)
            ):
                return jsonify({"status": "error", "message": "Service not found"}), 404

        if service is None:
            service = db.session.execute(
                text("""
                    SELECT
                        id::text AS id,
                        business_id::text AS business_id,
                        duration_minutes,
                        is_active
                    FROM services
                    WHERE id = :service_id
                """),
                {"service_id": existing["service_id"]},
            ).mappings().first()

        business = db.session.execute(
            text("""
                SELECT
                    id::text AS id,
                    opening_time,
                    closing_time,
                    is_active
                FROM businesses
                WHERE id = :business_id
            """),
            {"business_id": business_id},
        ).mappings().first()

        new_scheduled_at = existing["scheduled_at"]
        if "scheduled_at" in updates:
            new_scheduled_at = parse_datetime(updates["scheduled_at"])
            if new_scheduled_at is None:
                return jsonify({
                    "status": "error",
                    "message": "Appointment date and time must use ISO 8601 format",
                }), 400

            if new_scheduled_at < datetime.now(timezone.utc):
                return jsonify({
                    "status": "error",
                    "message": "Appointments cannot be scheduled in the past",
                }), 400

        if "scheduled_at" in updates or "service_id" in updates:
            hours_error = validate_business_hours(
                business, new_scheduled_at, service["duration_minutes"]
            )
            if hours_error:
                return jsonify({"status": "error", "message": hours_error}), 400

            db.session.execute(
                text("SELECT id FROM businesses WHERE id = :business_id FOR UPDATE"),
                {"business_id": business_id},
            )

            if check_booking_conflict(
                business_id,
                updates.get("service_id", existing["service_id"]),
                new_scheduled_at,
                service["duration_minutes"],
                exclude_appointment_id=appointment_id,
            ):
                return jsonify({
                    "status": "error",
                    "message": "This appointment conflicts with an existing appointment",
                }), 409

        if "scheduled_at" in updates:
            updates["scheduled_at"] = new_scheduled_at

        if "customer_name" in updates and isinstance(updates["customer_name"], str):
            updates["customer_name"] = updates["customer_name"].strip()

        if "customer_phone" in updates and isinstance(updates["customer_phone"], str):
            updates["customer_phone"] = updates["customer_phone"].strip()

        if "customer_email" in updates:
            if isinstance(updates["customer_email"], str) and updates["customer_email"].strip():
                updates["customer_email"] = updates["customer_email"].strip()
            else:
                updates["customer_email"] = None

        if "notes" in updates:
            if isinstance(updates["notes"], str):
                updates["notes"] = updates["notes"].strip()
            else:
                updates["notes"] = None

        set_clause = ", ".join(f"{field} = :{field}" for field in updates)

        updates["appointment_id"] = appointment_id

        result = db.session.execute(
            text(f"""
                UPDATE appointments
                SET {set_clause},
                    updated_at = NOW()
                WHERE id = :appointment_id
                RETURNING
            """ + get_appointment_columns()),
            updates,
        ).mappings().first()

        db.session.commit()

        return jsonify({
            "status": "success",
            "message": "Appointment updated successfully",
            "appointment": serialize_appointment(result),
        }), 200

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Appointment update failed")

        return jsonify({
            "status": "error",
            "message": "Appointment update failed. Please try again.",
        }), 500


@appointment_bp.route("/<appointment_id>", methods=["DELETE"])
@token_required
def cancel_appointment(appointment_id):
    if not _is_uuid(appointment_id):
        return jsonify({"status": "error", "message": "Appointment not found"}), 404

    business_ids = accessible_business_ids(g.current_user["id"])

    try:
        existing = db.session.execute(
            text("""
                SELECT
                    id::text AS id,
                    business_id::text AS business_id,
                    status
                FROM appointments
                WHERE id = :appointment_id
            """),
            {"appointment_id": appointment_id},
        ).mappings().first()

        if not existing or str(existing["business_id"]) not in business_ids:
            return jsonify({"status": "error", "message": "Appointment not found"}), 404

        if existing["status"] == "completed":
            return jsonify({
                "status": "error",
                "message": "Completed appointments cannot be cancelled",
            }), 409

        result = db.session.execute(
            text("""
                UPDATE appointments
                SET status = 'cancelled',
                    updated_at = NOW()
                WHERE id = :appointment_id
                RETURNING
            """ + get_appointment_columns()),
            {"appointment_id": appointment_id},
        ).mappings().first()

        db.session.commit()

        return jsonify({
            "status": "success",
            "message": "Appointment cancelled successfully",
            "appointment": serialize_appointment(result),
        }), 200

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Appointment cancellation failed")

        return jsonify({
            "status": "error",
            "message": "Appointment cancellation failed. Please try again.",
        }), 500
