import re
import uuid as uuid_lib
from datetime import datetime, timezone, timedelta, date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..utils.display import clean_demo_service_description
from ..utils.rate_limit import rate_limiter
from .appointments import (
    parse_datetime,
    validate_customer_fields,
    check_booking_conflict,
    validate_business_hours,
    get_appointment_columns,
    serialize_appointment,
)
from .customer_auth import decode_customer_token


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
        working_days,
        timezone,
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


@public_bp.route("/businesses", methods=["GET"])
@public_bp.route("/businesses", methods=["GET"])
def public_businesses():
    rows = db.session.execute(text("""
        SELECT
            id::text AS id,
            business_name,
            business_type,
            description,
            address,
            phone,
            opening_time::text AS opening_time,
            closing_time::text AS closing_time
        FROM businesses
        WHERE is_active = TRUE
        ORDER BY business_name
    """)).mappings().all()

    return jsonify({
        "businesses": [dict(row) for row in rows]
    }), 200

@public_bp.route("/businesses/<business_id>/services", methods=["GET"])
def public_business_services(business_id):
    rows = db.session.execute(text("""
        SELECT s.id::text AS id, s.service_name, s.description,
               s.duration_minutes, s.price
        FROM services s JOIN businesses b ON b.id=s.business_id
        WHERE b.id=:business_id AND b.is_active=TRUE AND s.is_active=TRUE
        ORDER BY s.service_name
    """), {"business_id": business_id}).mappings().all()
    services = []
    for row in rows:
        service = dict(row)
        service["description"] = clean_demo_service_description(
            service.get("description")
        )
        services.append(service)
    return jsonify({"services": services}), 200


@public_bp.route("/availability", methods=["GET"])
def public_availability():
    business_id = request.args.get("business_id")
    service_id = request.args.get("service_id")
    day_text = request.args.get("date")
    try:
        day = date.fromisoformat(day_text or "")
    except ValueError:
        return jsonify({"message": "A valid date is required"}), 400
    if day < datetime.now(timezone.utc).date():
        return jsonify({"date": day.isoformat(), "slots": []}), 200
    biz = db.session.execute(text("""
        SELECT opening_time, closing_time, working_days, timezone,
               booking_interval_minutes FROM businesses
        WHERE id=:business_id AND is_active=TRUE
    """), {"business_id": business_id}).mappings().first()
    svc = db.session.execute(text("""
        SELECT duration_minutes FROM services
        WHERE id=:service_id AND business_id=:business_id AND is_active=TRUE
    """), {"service_id": service_id, "business_id": business_id}).mappings().first()
    if not biz or not svc:
        return jsonify({"message": "Business or service not found"}), 404
    if not biz["opening_time"] or not biz["closing_time"]:
        return jsonify({"date": day.isoformat(), "slots": [], "message": "Business hours have not been configured"}), 200
    try:
        business_timezone = ZoneInfo(biz["timezone"] or "UTC")
    except ZoneInfoNotFoundError:
        return jsonify({"message": "Business timezone is invalid"}), 500
    if day.weekday() not in (biz["working_days"] or []):
        return jsonify({"date": day.isoformat(), "slots": [], "message": "Business is closed on this day"}), 200
    opening = datetime.combine(day, biz["opening_time"], business_timezone).astimezone(timezone.utc)
    closing = datetime.combine(day, biz["closing_time"], business_timezone).astimezone(timezone.utc)
    if closing <= opening:
        closing += timedelta(days=1)
    duration = svc["duration_minutes"]
    rows = db.session.execute(text("""
        SELECT a.scheduled_at, s.duration_minutes FROM appointments a
        JOIN services s ON s.id=a.service_id
        WHERE a.business_id=:business_id
          AND a.status IN ('booked','confirmed','checked_in')
          AND a.scheduled_at < :closing
          AND a.scheduled_at + make_interval(mins => s.duration_minutes) > :opening
    """), {"business_id": business_id, "opening": opening, "closing": closing}).mappings().all()
    occupied = [(r["scheduled_at"], r["scheduled_at"] + timedelta(minutes=r["duration_minutes"])) for r in rows]
    slots = []
    cursor = opening
    now = datetime.now(timezone.utc)
    interval = biz["booking_interval_minutes"] or 15
    while cursor + timedelta(minutes=duration) <= closing:
        end = cursor + timedelta(minutes=duration)
        if cursor > now and not any(start < end and cursor < finish for start, finish in occupied):
            local_start = cursor.astimezone(business_timezone)
            local_end = end.astimezone(business_timezone)
            slots.append({
                "start": cursor.isoformat(),
                "end": end.isoformat(),
                "label": f"{local_start:%I:%M %p} – {local_end:%I:%M %p}",
            })
        cursor += timedelta(minutes=interval)
    return jsonify({"date": day.isoformat(), "duration_minutes": duration, "slots": slots}), 200


@public_bp.route("/bookings", methods=["POST"])
@rate_limiter.limit(20, 60)
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
        customer_id = None
        booking_customer = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header:
            if not auth_header.startswith("Bearer "):
                return jsonify({
                    "status": "error",
                    "message": "Invalid customer authentication token",
                }), 401
            customer_id = decode_customer_token(auth_header.split(" ", 1)[1].strip())
            if not customer_id:
                return jsonify({
                    "status": "error",
                    "message": "Invalid customer authentication token",
                }), 401
            active_customer = db.session.execute(
                text("""
                    SELECT id::text AS id, full_name, phone, email
                    FROM customers
                    WHERE id = :customer_id
                      AND is_active = TRUE
                """),
                {"customer_id": customer_id},
            ).mappings().first()
            if not active_customer:
                return jsonify({
                    "status": "error",
                    "message": "Customer account not found or inactive",
                }), 401
            booking_customer = active_customer

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
                "business_id": business["id"],
                "service_id": service_id,
                "customer_name": (
                    booking_customer["full_name"]
                    if booking_customer
                    else data["customer_name"].strip()
                ),
                "customer_phone": (
                    booking_customer["phone"] or data["customer_phone"].strip()
                    if booking_customer
                    else data["customer_phone"].strip()
                ),
                "customer_email": (
                    booking_customer["email"]
                    if booking_customer
                    else data["customer_email"].strip()
                    if isinstance(data.get("customer_email"), str)
                    and data["customer_email"].strip()
                    else None
                ),
                "customer_id": customer_id,
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
