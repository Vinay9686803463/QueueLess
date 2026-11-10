import re
import uuid as uuid_lib
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from .appointments import (
    parse_datetime,
    validate_customer_fields,
    check_booking_conflict,
    validate_business_hours,
    get_appointment_columns,
    serialize_appointment,
)


public_bp = Blueprint(
    "public",
    __name__,
    url_prefix="/api/public",
)


def _is_uuid(value):
    try:
        uuid_lib.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def _slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return slug or "business"


def _businesses_has_slug_column():
    try:
        return bool(
            db.session.execute(
                text("""
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'businesses'
                      AND column_name = 'slug'
                """)
            ).scalar()
        )
    except Exception:
        db.session.rollback()
        return False


def _public_business_columns():
    return """
        id::text AS id,
        business_name,
        business_type,
        description,
        address,
        phone,
        email,
        opening_time,
        closing_time,
        average_service_time
    """


def _serialize_public_business(row):
    if row is None:
        return None

    business = dict(row)

    for field in ("opening_time", "closing_time"):
        value = business.get(field)
        if value is not None and hasattr(value, "strftime"):
            business[field] = value.strftime("%H:%M")

    return business


def _get_public_business(identifier):
    if not isinstance(identifier, str) or not identifier.strip():
        return None

    identifier = identifier.strip().lower()

    if _is_uuid(identifier):
        where_clause = "id = :identifier"
        params = {"identifier": identifier}
    else:
        where_clause = """
            is_active = TRUE
            AND lower(trim(both '-' from regexp_replace(
                business_name,
                '[^a-zA-Z0-9]+',
                '-',
                'g'
            ))) = :identifier
        """
        params = {"identifier": identifier}

    try:
        query = """
            SELECT
        """ + _public_business_columns() + """
            FROM businesses
            WHERE is_active = TRUE
              AND """ + where_clause + """
            ORDER BY created_at DESC
            LIMIT 2
        """
        rows = db.session.execute(text(query), params).mappings().all()

        if len(rows) != 1:
            return None

        return rows[0]
    except Exception:
        db.session.rollback()
        return None


@public_bp.route("/bookings", methods=["POST"])
def public_book_appointment():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "status": "error",
            "message": "A valid JSON object is required",
        }), 400

    business_identifier = data.get("business_id") or data.get("business_slug") or data.get("slug")
    service_id = data.get("service_id")

    if not business_identifier:
        return jsonify({
            "status": "error",
            "message": "Business ID or slug is required",
        }), 400

    if not _is_uuid(service_id):
        return jsonify({
            "status": "error",
            "message": "Invalid service ID",
        }), 400

    business = _get_public_business(business_identifier)
    if not business:
        return jsonify({
            "status": "error",
            "message": "Business not found",
        }), 404

    error = validate_customer_fields(data, creating=True)
    if error:
        return jsonify({
            "status": "error",
            "message": error,
        }), 400

    scheduled_at = parse_datetime(data.get("scheduled_at") or data.get("appointment_time"))
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

    try:
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
            or str(service["business_id"]) != str(business["id"])
        ):
            return jsonify({
                "status": "error",
                "message": "Service not found",
            }), 404

        hours_error = validate_business_hours(
            business, scheduled_at, service["duration_minutes"]
        )
        if hours_error:
            return jsonify({
                "status": "error",
                "message": hours_error,
            }), 400

        db.session.execute(
            text("SELECT id FROM businesses WHERE id = :business_id FOR UPDATE"),
            {"business_id": business["id"]},
        )

        if check_booking_conflict(
            business["id"],
            service_id,
            scheduled_at,
            service["duration_minutes"],
        ):
            return jsonify({
                "status": "error",
                "message": "This appointment slot is unavailable",
            }), 409

        result = db.session.execute(
            text("""
                INSERT INTO appointments (
                    business_id,
                    service_id,
                    customer_name,
                    customer_phone,
                    customer_email,
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
                    :scheduled_at,
                    'booked',
                    :notes
                )
                RETURNING
            """ + get_appointment_columns()),
            {
                "business_id": business["id"],
                "service_id": service_id,
                "customer_name": data["customer_name"].strip(),
                "customer_phone": data["customer_phone"].strip(),
                "customer_email": (
                    data["customer_email"].strip()
                    if isinstance(data.get("customer_email"), str)
                    and data["customer_email"].strip()
                    else None
                ),
                "scheduled_at": scheduled_at,
                "notes": (
                    data["notes"].strip()
                    if isinstance(data.get("notes"), str)
                    else None
                ),
            },
        ).mappings().first()

        db.session.commit()

        appointment = serialize_appointment(result)

        return jsonify({
            "status": "success",
            "message": "Appointment booked successfully",
            "appointment_id": appointment["id"],
            "appointment": appointment,
            "business": {
                "id": business["id"],
                "business_name": business["business_name"],
            },
            "service": {
                "id": service_id,
                "duration_minutes": service["duration_minutes"],
            },
        }), 201

    except IntegrityError:
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": "This appointment slot is unavailable",
        }), 409

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Public appointment booking failed")
        return jsonify({
            "status": "error",
            "message": "Appointment booking failed. Please try again.",
        }), 500
