import secrets
import uuid as uuid_lib
from datetime import datetime, timezone, timedelta, time
from urllib.parse import urlparse

from flask import Blueprint, request, jsonify, g, current_app
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from ..extensions import db
from ..utils.rate_limit import rate_limiter
from .auth import token_required
from .customer_auth import decode_customer_token
from .appointments import accessible_business_ids


queue_bp = Blueprint(
    "queue",
    __name__,
    url_prefix="/api",
)

QUEUE_STATUSES_AHEAD = ("waiting", "called", "serving")
MAX_TRACKING_RETRIES = 3
DEMO_QUEUE_SIZE = 12
DEMO_TRACKING_PREFIX = "DEMO-"
DEMO_CUSTOMER_NAMES = (
    "Avery Bennett", "Jordan Rivera", "Morgan Chen", "Riley Thompson",
    "Casey Patel", "Quinn Foster", "Taylor Brooks", "Cameron Lee",
    "Skyler Morgan", "Reese Walker", "Emerson Carter", "Rowan Kim",
    "Parker Ellis", "Finley Cooper", "Dakota Hayes", "Sage Mitchell",
    "Jamie Clarke", "Kendall Ross", "Alex Monroe", "Drew Bailey",
)


def _demo_data_enabled():
    if not current_app.config.get("QUEUELESS_ENABLE_DEMO_DATA", False):
        return False
    if current_app.config.get("ENV") != "development":
        return False

    database_host = urlparse(
        current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    ).hostname
    return database_host in {"localhost", "127.0.0.1", "::1"}


def _is_uuid(value):
    try:
        uuid_lib.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def queue_date_today():
    # The database stores dates in UTC and no business timezone column exists.
    return datetime.now(timezone.utc).date()


def _business_working_days(business_id):
    """Read optional legacy schedule data only when that schema column exists."""
    has_column = db.session.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name='businesses'
              AND column_name='working_days'
        )
    """)).scalar()
    if not has_column:
        return {0, 1, 2, 3, 4}
    days = db.session.execute(text("""
        SELECT working_days FROM businesses WHERE id=:business_id
    """), {"business_id": business_id}).scalar()
    try:
        return {int(day) for day in days if 0 <= int(day) <= 6}
    except (TypeError, ValueError):
        return {0, 1, 2, 3, 4}


def generate_token_number(business_id, queue_date):
    db.session.execute(
        text("""
            INSERT INTO queue_daily_counters (
                business_id, queue_date, next_token_number
            )
            VALUES (
                :business_id,
                :queue_date,
                COALESCE(
                    (
                        SELECT MAX(token_number) + 1
                        FROM queue_tokens
                        WHERE business_id = :business_id
                          AND queue_date = :queue_date
                    ),
                    1
                )
            )
            ON CONFLICT (business_id, queue_date)
            DO UPDATE SET next_token_number = GREATEST(
                queue_daily_counters.next_token_number,
                EXCLUDED.next_token_number
            )
        """),
        {"business_id": business_id, "queue_date": queue_date},
    )

    next_number = db.session.execute(
        text("""
            SELECT next_token_number
            FROM queue_daily_counters
            WHERE business_id = :business_id
              AND queue_date = :queue_date
            FOR UPDATE
        """),
        {"business_id": business_id, "queue_date": queue_date},
    ).scalar()

    db.session.execute(
        text("""
            UPDATE queue_daily_counters
            SET next_token_number = next_token_number + 1
            WHERE business_id = :business_id
              AND queue_date = :queue_date
        """),
        {"business_id": business_id, "queue_date": queue_date},
    )

    return next_number


def queue_token_columns():
    return """
        id::text AS id,
        business_id::text AS business_id,
        service_id::text AS service_id,
        appointment_id::text AS appointment_id,
        customer_name,
        customer_phone,
        customer_id::text AS customer_id,
        token_number,
        queue_date,
        tracking_code,
        status,
        joined_at,
        called_at,
        service_started_at,
        completed_at,
        created_at,
        updated_at
    """


def serialize_queue_token(row):
    if row is None:
        return None

    token = dict(row)

    for field in ("joined_at", "called_at", "service_started_at", "completed_at", "created_at", "updated_at"):
        value = token.get(field)
        if value is not None and hasattr(value, "isoformat"):
            token[field] = value.isoformat()

    if token.get("queue_date") is not None and hasattr(token["queue_date"], "isoformat"):
        token["queue_date"] = token["queue_date"].isoformat()

    return token


def customers_ahead(business_id, queue_date, token_number):
    return db.session.execute(
        text("""
            SELECT COUNT(*)::int
            FROM queue_tokens
            WHERE business_id = :business_id
              AND queue_date = :queue_date
              AND token_number < :token_number
              AND status IN ('waiting', 'called', 'serving')
        """),
        {
            "business_id": business_id,
            "queue_date": queue_date,
            "token_number": token_number,
        },
    ).scalar() or 0


@queue_bp.route("/appointments/<appointment_id>/check-in", methods=["POST"])
@token_required
def check_in_appointment(appointment_id):
    if not _is_uuid(appointment_id):
        return jsonify({"status": "error", "message": "Appointment not found"}), 404

    business_ids = accessible_business_ids(g.current_user["id"])

    try:
        appointment = db.session.execute(
            text("""
                SELECT
                    id::text AS id,
                    business_id::text AS business_id,
                    service_id::text AS service_id,
                    status
                FROM appointments
                WHERE id = :appointment_id
            """),
            {"appointment_id": appointment_id},
        ).mappings().first()

        if not appointment or str(appointment["business_id"]) not in business_ids:
            return jsonify({"status": "error", "message": "Appointment not found"}), 404

        if appointment["status"] not in ("booked", "confirmed"):
            return jsonify({
                "status": "error",
                "message": "Appointment is not eligible for check-in",
            }), 409

        existing_token = db.session.execute(
            text("""
                SELECT id::text AS id
                FROM queue_tokens
                WHERE appointment_id = :appointment_id
            """),
            {"appointment_id": appointment_id},
        ).mappings().first()

        if existing_token:
            return jsonify({
                "status": "error",
                "message": "Appointment has already been checked in",
            }), 409

        business_id = appointment["business_id"]
        service_id = appointment["service_id"]
        today = queue_date_today()

        for _ in range(MAX_TRACKING_RETRIES):
            try:
                token_number = generate_token_number(business_id, today)
                tracking_code = secrets.token_hex(16)

                result = db.session.execute(
                    text("""
                        INSERT INTO queue_tokens (
                            business_id,
                            service_id,
                            appointment_id,
                            customer_name,
                            customer_phone,
                            token_number,
                            queue_date,
                            tracking_code,
                            status
                        )
                        SELECT
                            :business_id,
                            :service_id,
                            :appointment_id,
                            a.customer_name,
                            a.customer_phone,
                            :token_number,
                            :queue_date,
                            :tracking_code,
                            'waiting'
                        FROM appointments a
                        WHERE a.id = :appointment_id
                        RETURNING
                    """ + queue_token_columns()),
                    {
                        "business_id": business_id,
                        "service_id": service_id,
                        "appointment_id": appointment_id,
                        "token_number": token_number,
                        "queue_date": today,
                        "tracking_code": tracking_code,
                    },
                ).mappings().first()

                db.session.execute(
                    text("""
                        UPDATE appointments
                        SET status = 'checked_in',
                            updated_at = NOW()
                        WHERE id = :appointment_id
                    """),
                    {"appointment_id": appointment_id},
                )

                db.session.commit()

                token = serialize_queue_token(result)
                token["customers_ahead"] = customers_ahead(
                    business_id, today, token["token_number"]
                )

                return jsonify({
                    "status": "success",
                    "message": "Appointment checked in successfully",
                    "queue_token": token,
                }), 201

            except IntegrityError:
                db.session.rollback()

                duplicate = db.session.execute(
                    text("""
                        SELECT id::text AS id
                        FROM queue_tokens
                        WHERE appointment_id = :appointment_id
                    """),
                    {"appointment_id": appointment_id},
                ).mappings().first()

                if duplicate:
                    return jsonify({
                        "status": "error",
                        "message": "Appointment has already been checked in",
                    }), 409

                # Retry only for rare tracking-code collisions.
                continue

        return jsonify({
            "status": "error",
            "message": "Unable to generate a unique tracking code",
        }), 500

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Appointment check-in failed")

        return jsonify({
            "status": "error",
            "message": "Appointment check-in failed. Please try again.",
        }), 500


@queue_bp.route("/public/walk-in", methods=["POST"])
@rate_limiter.limit(20, 60)
def walk_in():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "status": "error",
            "message": "A valid JSON object is required",
        }), 400

    business_id = data.get("business_id")
    service_id = data.get("service_id")
    customer_name = data.get("customer_name")
    customer_phone = data.get("customer_phone")

    # Derive customer identity from the verified customer token.
    customer_id = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        customer_id = decode_customer_token(auth_header.split(" ", 1)[1].strip())

    if not _is_uuid(business_id):
        return jsonify({"status": "error", "message": "Invalid business ID"}), 400

    if not _is_uuid(service_id):
        return jsonify({"status": "error", "message": "Invalid service ID"}), 400

    if not isinstance(customer_name, str) or not customer_name.strip():
        return jsonify({"status": "error", "message": "Customer name is required"}), 400

    if not isinstance(customer_phone, str) or not customer_phone.strip():
        return jsonify({"status": "error", "message": "Customer phone is required"}), 400

    if len(customer_name.strip()) > 120:
        return jsonify({"status": "error", "message": "Customer name cannot exceed 120 characters"}), 400

    if len(customer_phone.strip()) > 20:
        return jsonify({"status": "error", "message": "Customer phone cannot exceed 20 characters"}), 400

    today = queue_date_today()

    try:
        business = db.session.execute(
            text("""
                SELECT
                    id::text AS id,
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

        for _ in range(MAX_TRACKING_RETRIES):
            try:
                token_number = generate_token_number(business_id, today)
                tracking_code = secrets.token_hex(16)

                result = db.session.execute(
                    text("""
                        INSERT INTO queue_tokens (
                            business_id,
                            service_id,
                            appointment_id,
                            customer_name,
                            customer_phone,
                            customer_id,
                            token_number,
                            queue_date,
                            tracking_code,
                            status
                        )
                        VALUES (
                            :business_id,
                            :service_id,
                            NULL,
                            :customer_name,
                            :customer_phone,
                            :customer_id,
                            :token_number,
                            :queue_date,
                            :tracking_code,
                            'waiting'
                        )
                        RETURNING
                    """ + queue_token_columns()),
                    {
                        "business_id": business_id,
                        "service_id": service_id,
                        "customer_name": customer_name.strip(),
                        "customer_phone": customer_phone.strip(),
                        "customer_id": customer_id,
                        "token_number": token_number,
                        "queue_date": today,
                        "tracking_code": tracking_code,
                    },
                ).mappings().first()

                db.session.commit()

                token = serialize_queue_token(result)
                ahead = customers_ahead(business_id, today, token["token_number"])
                token["customers_ahead"] = ahead
                token["estimated_wait_minutes"] = ahead * (service["duration_minutes"] or 0)

                return jsonify({
                    "status": "success",
                    "message": "Walk-in registered successfully",
                    "queue_token": token,
                }), 201

            except IntegrityError:
                db.session.rollback()
                continue

        return jsonify({
            "status": "error",
            "message": "Unable to generate a unique tracking code",
        }), 500

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Walk-in registration failed")

        return jsonify({
            "status": "error",
            "message": "Walk-in registration failed. Please try again.",
        }), 500


@queue_bp.route("/public/track/<tracking_code>", methods=["GET"])
def track_queue_token(tracking_code):
    if not isinstance(tracking_code, str) or len(tracking_code.strip()) != 32:
        return jsonify({"status": "error", "message": "Tracking code not found"}), 404

    try:
        token = db.session.execute(
            text("""
                SELECT
                    qt.token_number,
                    qt.queue_date,
                    qt.status,
                    b.business_name,
                    s.service_name,
                    s.duration_minutes,
                    qt.business_id::text AS business_id
                FROM queue_tokens qt
                JOIN businesses b ON b.id = qt.business_id
                JOIN services s ON s.id = qt.service_id
                WHERE qt.tracking_code = :tracking_code
            """),
            {"tracking_code": tracking_code.strip()},
        ).mappings().first()

        if not token:
            return jsonify({"status": "error", "message": "Tracking code not found"}), 404

        ahead = customers_ahead(
            token["business_id"],
            token["queue_date"],
            token["token_number"],
        )

        return jsonify({
            "status": "success",
            "tracking": {
                "token_number": token["token_number"],
                "queue_status": token["status"],
                "business_name": token["business_name"],
                "service_name": token["service_name"],
                "customers_ahead": ahead,
                "estimated_wait_minutes": ahead * (token["duration_minutes"] or 0),
            },
        }), 200

    except Exception:
        current_app.logger.exception("Queue tracking failed")

        return jsonify({
            "status": "error",
            "message": "Unable to track queue entry",
        }), 500


def _queue_paused_column_exists():
    try:
        result = db.session.execute(
            text("""
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'businesses'
                  AND column_name = 'queue_paused'
            """)
        ).scalar()
        return bool(result)
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Queue pause migration check failed")
        return False


def _is_queue_paused(business_id):
    if not _queue_paused_column_exists():
        return False

    try:
        return bool(db.session.execute(
            text("""
                SELECT queue_paused
                FROM businesses
                WHERE id = :business_id
            """),
            {"business_id": business_id},
        ).scalar())
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Queue paused state read failed")
        return False


def _queue_token_with_service(token_id, business_id=None):
    query = """
        SELECT
            qt.id::text AS id,
            qt.business_id::text AS business_id,
            qt.service_id::text AS service_id,
            qt.appointment_id::text AS appointment_id,
            qt.customer_name,
            qt.customer_phone,
            qt.tracking_code LIKE 'DEMO-%' AS is_demo,
            qt.token_number,
            qt.queue_date,
            qt.tracking_code,
            qt.status,
            qt.joined_at,
            qt.called_at,
            qt.service_started_at,
            qt.completed_at,
            qt.created_at,
            qt.updated_at,
            s.service_name,
            s.duration_minutes
        FROM queue_tokens qt
        JOIN services s ON s.id = qt.service_id
        WHERE qt.id = :token_id
    """
    params = {"token_id": token_id}

    if business_id is not None:
        query += " AND qt.business_id = :business_id"
        params["business_id"] = business_id

    row = db.session.execute(text(query), params).mappings().first()
    if row is None:
        return None

    token = serialize_queue_token(row)
    token["service_name"] = row["service_name"]
    token["duration_minutes"] = row["duration_minutes"]
    return token


@queue_bp.route("/businesses/<business_id>/queue", methods=["GET"])
@token_required
def get_queue(business_id):
    if not _is_uuid(business_id):
        return jsonify({"status": "error", "message": "Business not found"}), 404

    user_id = g.current_user["id"]
    if business_id not in accessible_business_ids(user_id):
        return jsonify({"status": "error", "message": "Business not found"}), 404

    today = queue_date_today()
    requested_date = request.args.get("date")

    if requested_date:
        try:
            selected_date = datetime.strptime(
                requested_date, "%Y-%m-%d"
            ).date()
        except ValueError:
            return jsonify({
                "status": "error",
                "message": "Invalid queue date. Use YYYY-MM-DD.",
            }), 400
    else:
        selected_date = today

    try:
        rows = db.session.execute(
            text("""
                SELECT
                    qt.id::text AS id,
                    qt.business_id::text AS business_id,
                    qt.service_id::text AS service_id,
                    qt.appointment_id::text AS appointment_id,
                    qt.customer_name,
                    qt.customer_phone,
                    qt.tracking_code LIKE 'DEMO-%' AS is_demo,
                    qt.token_number,
                    qt.queue_date,
                    qt.tracking_code,
                    qt.status,
                    qt.joined_at,
                    qt.called_at,
                    qt.service_started_at,
                    qt.completed_at,
                    qt.created_at,
                    qt.updated_at,
                    s.service_name,
                    s.duration_minutes
                FROM queue_tokens qt
                JOIN services s ON s.id = qt.service_id
                WHERE qt.business_id = :business_id
                  AND qt.queue_date = :queue_date
                ORDER BY qt.token_number ASC
            """),
            {"business_id": business_id, "queue_date": selected_date},
        ).mappings().all()

        waiting = []
        called = []
        completed = []
        skipped = []
        cancelled = []

        for row in rows:
            token = serialize_queue_token(row)
            token["service_name"] = row["service_name"]
            token["duration_minutes"] = row["duration_minutes"]

            if row["status"] == "waiting":
                token["queue_position"] = len(waiting) + 1
                token["estimated_wait_minutes"] = len(waiting) * (row["duration_minutes"] or 0)
                waiting.append(token)
            elif row["status"] in ("called", "serving"):
                called.append(token)
            elif row["status"] == "completed":
                completed.append(token)
            elif row["status"] == "skipped":
                skipped.append(token)
            elif row["status"] == "cancelled":
                cancelled.append(token)

        queue_pause_supported = _queue_paused_column_exists()
        return jsonify({
            "status": "success",
            "business_id": business_id,
            "queue_date": selected_date.isoformat(),
            "queue_paused": (
                _is_queue_paused(business_id) if queue_pause_supported else False
            ),
            "queue_pause_supported": queue_pause_supported,
            "summary": {
                "total": len(rows),
                "waiting": len(waiting),
                "called": len(called),
                "completed": len(completed),
                "skipped": len(skipped),
                "cancelled": len(cancelled),
            },
            "current": called[0] if called else None,
            "waiting": waiting,
            "called": called,
            "completed": completed,
            "skipped": skipped,
            "cancelled": cancelled,
        }), 200

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Queue retrieval failed")
        return jsonify({"status": "error", "message": "Unable to retrieve queue"}), 500


@queue_bp.route("/businesses/<business_id>/queue/demo", methods=["POST"])
@token_required
def seed_demo_queue(business_id):
    if not _demo_data_enabled():
        return jsonify({
            "status": "error",
            "message": "Demo queue data is available only in explicitly enabled local development.",
        }), 404
    if not _is_uuid(business_id):
        return jsonify({"status": "error", "message": "Business not found"}), 404

    user_id = g.current_user["id"]
    if business_id not in accessible_business_ids(user_id):
        return jsonify({"status": "error", "message": "Business not found"}), 404

    try:
        business = db.session.execute(
            text("""
                SELECT id, opening_time, closing_time
                FROM businesses
                WHERE id = :business_id AND is_active = TRUE
                FOR UPDATE
            """),
            {"business_id": business_id},
        ).mappings().first()
        if not business:
            db.session.rollback()
            return jsonify({"status": "error", "message": "Business not found"}), 404

        services = db.session.execute(
            text("""
                SELECT
                    id::text AS id,
                    COALESCE(duration_minutes, 60) AS duration_minutes
                FROM services
                WHERE business_id = :business_id AND is_active = TRUE
                ORDER BY created_at, id
            """),
            {"business_id": business_id},
        ).mappings().all()
        if not services:
            db.session.rollback()
            return jsonify({
                "status": "error",
                "message": "Add an active service before generating demo queue entries.",
            }), 409

        compact_id = business_id.replace("-", "")
        marker_prefix = f"DEMO-GENERATED:{compact_id}:"
        existing_appointments = db.session.execute(text("""
            SELECT
                a.id::text AS id,
                a.notes,
                a.service_id::text AS service_id,
                a.scheduled_at,
                COALESCE(s.duration_minutes, 60) AS duration_minutes
            FROM appointments a
            LEFT JOIN services s ON s.id = a.service_id
            WHERE a.business_id = :business_id
              AND a.notes LIKE :marker_prefix
            FOR UPDATE OF a
        """), {"business_id": business_id, "marker_prefix": f"{marker_prefix}%"}).mappings().all()
        appointments_by_index = {}
        for appointment in existing_appointments:
            try:
                index = int(appointment["notes"].rsplit(":", 1)[1])
                if 1 <= index <= DEMO_QUEUE_SIZE:
                    appointments_by_index[index] = dict(appointment)
            except (TypeError, ValueError):
                continue
        already_generated = len(appointments_by_index)

        occupied = db.session.execute(text("""
            SELECT
                a.scheduled_at,
                COALESCE(s.duration_minutes, 60) AS duration_minutes
            FROM appointments a
            JOIN services s ON s.id = a.service_id
            WHERE a.business_id = :business_id
              AND a.status IN ('booked','confirmed','checked_in')
        """), {"business_id": business_id}).mappings().all()
        intervals = [(row["scheduled_at"], row["scheduled_at"] + timedelta(minutes=row["duration_minutes"])) for row in occupied]
        opening = business["opening_time"] or time(9, 0)
        working_days = _business_working_days(business_id)
        closing = business["closing_time"]
        closing_minutes = closing.hour * 60 + closing.minute if closing else opening.hour * 60 + opening.minute + 12 * 60
        opening_minutes = opening.hour * 60 + opening.minute
        if closing_minutes <= opening_minutes:
            closing_minutes += 24 * 60

        # Schedule only missing appointments. Start on the next future opening,
        # distribute work across weekdays when the business day is shorter than 12h.
        slots = {}
        pending = [n for n in range(1, DEMO_QUEUE_SIZE + 1) if n not in appointments_by_index]
        cursor_day = datetime.now(timezone.utc).date()
        now = datetime.now(timezone.utc)
        search_days = 0
        while pending and search_days < 370:
            if cursor_day.weekday() not in working_days:
                cursor_day += timedelta(days=1)
                search_days += 1
                continue
            day_open = datetime.combine(cursor_day, time(opening_minutes // 60 % 24, opening_minutes % 60), timezone.utc)
            day_close = datetime.combine(cursor_day, time(closing_minutes // 60 % 24, closing_minutes % 60), timezone.utc)
            if closing_minutes >= 24 * 60:
                day_close += timedelta(days=1)
            if cursor_day == now.date() and now > day_open:
                next_slot = now.replace(minute=0, second=0, microsecond=0)
                if next_slot < now:
                    next_slot += timedelta(hours=1)
                day_open = max(day_open, next_slot)
            day_conflicts = sorted((start, end) for start, end in intervals if start < day_close and end > day_open)
            segments = []
            segment_start = day_open
            for conflict_start, conflict_end in day_conflicts:
                if conflict_start > segment_start:
                    segments.append((segment_start, conflict_start))
                segment_start = max(segment_start, conflict_end)
            if day_close > segment_start:
                segments.append((segment_start, day_close))
            # Allocate each demo appointment using its selected service duration.
            for idx in list(pending):
                service_duration = max(
                    1,
                    int(services[(idx - 1) % len(services)]["duration_minutes"] or 60),
                )
                required_time = timedelta(minutes=service_duration)

                segment_index = next(
                    (
                        position
                        for position, (start, end) in enumerate(segments)
                        if end - start >= required_time
                    ),
                    None,
                )
                if segment_index is None:
                    continue

                slot_start, segment_end = segments[segment_index]
                slot_end = slot_start + required_time

                slots[idx] = slot_start
                intervals.append((slot_start, slot_end))
                segments[segment_index] = (slot_end, segment_end)
                pending.remove(idx)
            cursor_day += timedelta(days=1)
            search_days += 1
        if pending:
            db.session.rollback()
            return jsonify({"status": "error", "message": "Could not fit demo appointments within configured business hours."}), 409

        now_db = datetime.now(timezone.utc)
        for index in range(1, DEMO_QUEUE_SIZE + 1):
            display_name = f"DEMO · {DEMO_CUSTOMER_NAMES[(index - 1) % len(DEMO_CUSTOMER_NAMES)]}"
            phone = f"555-01{index:02d}"
            email = f"demo-{compact_id}-{index:02d}@queueless.local"
            customer = db.session.execute(text("""
                SELECT id::text AS id, full_name FROM customers WHERE email = :email FOR UPDATE
            """), {"email": email}).mappings().first()
            if customer and customer["full_name"] != display_name:
                db.session.rollback()
                return jsonify({"status": "error", "message": "Demo customer identifier conflicts with an existing account."}), 409
            if not customer:
                customer = db.session.execute(text("""
                    INSERT INTO customers (full_name,email,phone,password_hash,is_active)
                    VALUES (:name,:email,:phone,:password_hash,TRUE)
                    RETURNING id::text AS id, full_name
                """), {"name": display_name, "email": email, "phone": phone,
                       "password_hash": generate_password_hash(secrets.token_urlsafe(32))}).mappings().first()
            appointment = appointments_by_index.get(index)
            service_id = services[(index - 1) % len(services)]["id"]
            if not appointment:
                scheduled_at = slots[index]
                appointment = db.session.execute(text("""
                    INSERT INTO appointments (
                        business_id,service_id,customer_name,customer_phone,customer_email,
                        customer_id,scheduled_at,status,notes
                    ) VALUES (
                        :business_id,:service_id,:name,:phone,:email,:customer_id,
                        :scheduled_at,'confirmed',:notes
                    ) RETURNING id::text AS id, scheduled_at, service_id::text AS service_id
                """), {"business_id": business_id, "service_id": service_id,
                       "name": display_name, "phone": phone, "email": email,
                       "customer_id": customer["id"], "scheduled_at": scheduled_at,
                       "notes": f"{marker_prefix}{index}"}).mappings().first()
                appointment = dict(appointment)
                appointments_by_index[index] = appointment
            else:
                appointment = dict(appointment)
                # Adopt existing demo appointments without changing their booked time.
                db.session.execute(text("""
                    UPDATE appointments SET customer_id=:customer_id,
                        customer_name=:name, customer_phone=:phone, customer_email=:email,
                        service_id=:service_id, updated_at=NOW()
                    WHERE id=:appointment_id
                """), {"customer_id": customer["id"], "name": display_name,
                       "phone": phone, "email": email, "service_id": service_id,
                       "appointment_id": appointment["id"]})

            queue_date = appointment["scheduled_at"].date()
            tracking_code = f"DEMO-{compact_id}-SLOT-{index:02d}"
            queue_entry = db.session.execute(text("""
                SELECT id FROM queue_tokens WHERE appointment_id=:appointment_id FOR UPDATE
            """), {"appointment_id": appointment["id"]}).first()
            if not queue_entry:
                queue_entry = db.session.execute(text("""
                    SELECT id FROM queue_tokens WHERE tracking_code=:tracking_code FOR UPDATE
                """), {"tracking_code": tracking_code}).first()
            if not queue_entry:
                legacy = db.session.execute(text("""
                    SELECT id FROM queue_tokens
                    WHERE business_id=:business_id AND customer_id IS NULL
                      AND appointment_id IS NULL AND tracking_code LIKE :prefix
                      AND right(tracking_code, 2)=:suffix
                    ORDER BY queue_date DESC, created_at DESC LIMIT 1 FOR UPDATE
                """), {"business_id": business_id,
                       "prefix": f"{DEMO_TRACKING_PREFIX}{compact_id}-%",
                       "suffix": f"{index:02d}"}).first()
                token_number = generate_token_number(business_id, queue_date)
                if legacy:
                    db.session.execute(text("""
                        UPDATE queue_tokens SET appointment_id=:appointment_id,
                            customer_id=:customer_id, service_id=:service_id,
                            customer_name=:name, customer_phone=:phone,
                            token_number=:token_number, queue_date=:queue_date,
                            status='waiting', joined_at=:joined_at, updated_at=NOW()
                        WHERE id=:id
                    """), {"appointment_id": appointment["id"], "customer_id": customer["id"],
                           "service_id": appointment["service_id"], "name": display_name,
                           "phone": phone, "token_number": token_number,
                           "queue_date": queue_date, "joined_at": now_db, "id": legacy[0]})
                else:
                    db.session.execute(text("""
                        INSERT INTO queue_tokens (
                            business_id,service_id,appointment_id,customer_name,customer_phone,
                            customer_id,token_number,queue_date,tracking_code,status,joined_at
                        ) VALUES (
                            :business_id,:service_id,:appointment_id,:name,:phone,:customer_id,
                            :token_number,:queue_date,:tracking_code,'waiting',:joined_at
                        )
                    """), {"business_id": business_id, "service_id": appointment["service_id"],
                           "appointment_id": appointment["id"], "name": display_name,
                           "phone": phone, "customer_id": customer["id"],
                           "token_number": token_number, "queue_date": queue_date,
                           "tracking_code": tracking_code, "joined_at": now_db})
            else:
                db.session.execute(text("""
                    UPDATE queue_tokens SET appointment_id=:appointment_id,
                        customer_id=:customer_id, service_id=:service_id,
                        customer_name=:name, customer_phone=:phone,
                        queue_date=:queue_date, status='waiting', updated_at=NOW()
                    WHERE id=:id
                """), {"appointment_id": appointment["id"], "customer_id": customer["id"],
                       "service_id": appointment["service_id"], "name": display_name,
                       "phone": phone, "queue_date": queue_date, "id": queue_entry[0]})

        db.session.commit()
        total = db.session.execute(text("""
            SELECT COUNT(*) FROM appointments
            WHERE business_id=:business_id AND notes LIKE :marker
        """), {"business_id": business_id, "marker": f"{marker_prefix}%"}).scalar()

        return jsonify({
            "status": "success",
            "created": max(0, DEMO_QUEUE_SIZE - already_generated),
            "total_demo_entries": DEMO_QUEUE_SIZE,
            "total_demo_appointments": total,
            "message": "Demo customers, appointments, and linked queue entries are ready.",
        }), 201 if already_generated < DEMO_QUEUE_SIZE else 200
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Demo queue seeding failed")
        return jsonify({
            "status": "error",
            "message": "Unable to generate demo queue entries.",
        }), 500


@queue_bp.route("/businesses/<business_id>/queue/demo", methods=["DELETE"])
@token_required
def remove_demo_queue(business_id):
    if not _demo_data_enabled():
        return jsonify({
            "status": "error",
            "message": "Demo queue data is available only in explicitly enabled local development.",
        }), 404
    if not _is_uuid(business_id):
        return jsonify({"status": "error", "message": "Business not found"}), 404

    user_id = g.current_user["id"]
    if business_id not in accessible_business_ids(user_id):
        return jsonify({"status": "error", "message": "Business not found"}), 404

    try:
        db.session.execute(
            text("""
                SELECT id
                FROM businesses
                WHERE id = :business_id AND is_active = TRUE
                FOR UPDATE
            """),
            {"business_id": business_id},
        )
        compact_id = business_id.replace("-", "")
        marker = f"DEMO-GENERATED:{compact_id}:%"
        linked_result = db.session.execute(text("""
            DELETE FROM queue_tokens
            WHERE business_id=:business_id AND appointment_id IN (
                SELECT id FROM appointments
                WHERE business_id=:business_id AND notes LIKE :marker
            ) RETURNING id
        """), {"business_id": business_id, "marker": marker})
        linked_removed = len(linked_result.fetchall())
        db.session.execute(text("""
            DELETE FROM appointments
            WHERE business_id=:business_id AND notes LIKE :marker
        """), {"business_id": business_id, "marker": marker})
        result = db.session.execute(
            text("""
                DELETE FROM queue_tokens
                WHERE business_id = :business_id
                  AND tracking_code LIKE :demo_prefix
                RETURNING id
            """),
            {
                "business_id": business_id,
                "demo_prefix": f"{DEMO_TRACKING_PREFIX}{business_id.replace('-', '')}-%",
            },
        )
        removed = linked_removed + len(result.fetchall())
        db.session.execute(text("""
            DELETE FROM customers c
            WHERE c.email LIKE :email_prefix
              AND c.full_name LIKE 'DEMO · %'
              AND NOT EXISTS (SELECT 1 FROM appointments a WHERE a.customer_id=c.id)
              AND NOT EXISTS (SELECT 1 FROM queue_tokens q WHERE q.customer_id=c.id)
        """), {"email_prefix": f"demo-{compact_id}-%@queueless.local"})
        db.session.commit()
        return jsonify({
            "status": "success",
            "removed": removed,
            "message": f"Removed {removed} demo queue entries.",
        }), 200
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Demo queue cleanup failed")
        return jsonify({
            "status": "error",
            "message": "Unable to remove demo queue entries.",
        }), 500


@queue_bp.route("/businesses/<business_id>/queue/call-next", methods=["POST"])
@token_required
def call_next_customer(business_id):
    if not _is_uuid(business_id):
        return jsonify({"status": "error", "message": "Business not found"}), 404

    user_id = g.current_user["id"]
    if business_id not in accessible_business_ids(user_id):
        return jsonify({"status": "error", "message": "Business not found"}), 404

    if _is_queue_paused(business_id):
        return jsonify({"status": "error", "message": "Queue is paused"}), 409

    today = queue_date_today()

    try:
        business = db.session.execute(
            text("""
                SELECT id
                FROM businesses
                WHERE id = :business_id AND is_active = TRUE
                FOR UPDATE
            """),
            {"business_id": business_id},
        ).first()
        if not business:
            db.session.rollback()
            return jsonify({"status": "error", "message": "Business not found"}), 404

        if _is_queue_paused(business_id):
            db.session.rollback()
            return jsonify({"status": "error", "message": "Queue is paused"}), 409

        active = db.session.execute(
            text("""
                SELECT id::text AS id
                FROM queue_tokens
                WHERE business_id = :business_id
                  AND queue_date = :queue_date
                  AND status IN ('called', 'serving')
                LIMIT 1
                FOR UPDATE
            """),
            {"business_id": business_id, "queue_date": today},
        ).mappings().first()

        if active:
            db.session.rollback()
            return jsonify({
                "status": "error",
                "message": "A customer is already being served",
            }), 409

        next_token = db.session.execute(
            text("""
                SELECT id::text AS id
                FROM queue_tokens
                WHERE business_id = :business_id
                  AND queue_date = :queue_date
                  AND status = 'waiting'
                ORDER BY token_number ASC
                LIMIT 1
                FOR UPDATE
            """),
            {"business_id": business_id, "queue_date": today},
        ).mappings().first()

        if not next_token:
            db.session.rollback()
            return jsonify({"status": "error", "message": "No waiting customers in queue"}), 404

        db.session.execute(
            text("""
                UPDATE queue_tokens
                SET status = 'called',
                    called_at = NOW(),
                    updated_at = NOW()
                WHERE id = :token_id
            """),
            {"token_id": next_token["id"]},
        )

        db.session.commit()

        token = _queue_token_with_service(next_token["id"], business_id)
        return jsonify({
            "status": "success",
            "message": "Next customer called",
            "queue_token": token,
        }), 200

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Call-next failed")
        return jsonify({"status": "error", "message": "Unable to call next customer"}), 500


@queue_bp.route("/businesses/<business_id>/queue/<token_id>/complete", methods=["POST"])
@token_required
def complete_queue_token(business_id, token_id):
    if not _is_uuid(business_id) or not _is_uuid(token_id):
        return jsonify({"status": "error", "message": "Queue entry not found"}), 404

    user_id = g.current_user["id"]
    if business_id not in accessible_business_ids(user_id):
        return jsonify({"status": "error", "message": "Business not found"}), 404

    try:
        token = db.session.execute(
            text("""
                SELECT id::text AS id, status
                FROM queue_tokens
                WHERE id = :token_id
                  AND business_id = :business_id
                FOR UPDATE
            """),
            {"token_id": token_id, "business_id": business_id},
        ).mappings().first()

        if not token:
            return jsonify({"status": "error", "message": "Queue entry not found"}), 404

        if token["status"] not in ("called", "serving"):
            return jsonify({
                "status": "error",
                "message": "Only called or serving customers can be completed",
            }), 409

        db.session.execute(
            text("""
                UPDATE queue_tokens
                SET status = 'completed',
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = :token_id
            """),
            {"token_id": token_id},
        )
        db.session.commit()

        updated = _queue_token_with_service(token_id, business_id)
        return jsonify({
            "status": "success",
            "message": "Customer completed",
            "queue_token": updated,
        }), 200

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Complete queue entry failed")
        return jsonify({"status": "error", "message": "Unable to complete queue entry"}), 500


@queue_bp.route("/businesses/<business_id>/queue/<token_id>/skip", methods=["POST"])
@token_required
def skip_queue_token(business_id, token_id):
    if not _is_uuid(business_id) or not _is_uuid(token_id):
        return jsonify({"status": "error", "message": "Queue entry not found"}), 404

    user_id = g.current_user["id"]
    if business_id not in accessible_business_ids(user_id):
        return jsonify({"status": "error", "message": "Business not found"}), 404

    try:
        token = db.session.execute(
            text("""
                SELECT id::text AS id, status
                FROM queue_tokens
                WHERE id = :token_id
                  AND business_id = :business_id
                FOR UPDATE
            """),
            {"token_id": token_id, "business_id": business_id},
        ).mappings().first()

        if not token:
            return jsonify({"status": "error", "message": "Queue entry not found"}), 404

        if token["status"] not in ("waiting", "called", "serving"):
            return jsonify({
                "status": "error",
                "message": "This queue entry cannot be skipped",
            }), 409

        db.session.execute(
            text("""
                UPDATE queue_tokens
                SET status = 'skipped',
                    updated_at = NOW()
                WHERE id = :token_id
            """),
            {"token_id": token_id},
        )
        db.session.commit()

        updated = _queue_token_with_service(token_id, business_id)
        return jsonify({
            "status": "success",
            "message": "Customer skipped",
            "queue_token": updated,
        }), 200

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Skip queue entry failed")
        return jsonify({"status": "error", "message": "Unable to skip queue entry"}), 500


@queue_bp.route("/businesses/<business_id>/queue/<token_id>/cancel", methods=["POST"])
@token_required
def cancel_queue_token(business_id, token_id):
    if not _is_uuid(business_id) or not _is_uuid(token_id):
        return jsonify({"status": "error", "message": "Queue entry not found"}), 404

    user_id = g.current_user["id"]
    if business_id not in accessible_business_ids(user_id):
        return jsonify({"status": "error", "message": "Business not found"}), 404

    try:
        token = db.session.execute(
            text("""
                SELECT id::text AS id, status
                FROM queue_tokens
                WHERE id = :token_id
                  AND business_id = :business_id
                FOR UPDATE
            """),
            {"token_id": token_id, "business_id": business_id},
        ).mappings().first()

        if not token:
            return jsonify({"status": "error", "message": "Queue entry not found"}), 404

        if token["status"] in ("completed", "skipped", "cancelled"):
            return jsonify({
                "status": "error",
                "message": "This queue entry cannot be cancelled",
            }), 409

        db.session.execute(
            text("""
                UPDATE queue_tokens
                SET status = 'cancelled',
                    updated_at = NOW()
                WHERE id = :token_id
            """),
            {"token_id": token_id},
        )
        db.session.commit()

        updated = _queue_token_with_service(token_id, business_id)
        return jsonify({
            "status": "success",
            "message": "Customer cancelled",
            "queue_token": updated,
        }), 200

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Cancel queue entry failed")
        return jsonify({"status": "error", "message": "Unable to cancel queue entry"}), 500


@queue_bp.route("/businesses/<business_id>/queue/pause", methods=["POST"])
@token_required
def pause_queue(business_id):
    if not _is_uuid(business_id):
        return jsonify({"status": "error", "message": "Business not found"}), 404

    user_id = g.current_user["id"]
    if business_id not in accessible_business_ids(user_id):
        return jsonify({"status": "error", "message": "Business not found"}), 404

    if not _queue_paused_column_exists():
        return jsonify({
            "status": "error",
            "message": "Queue pause requires database migration 001_add_queue_paused_to_businesses.sql",
        }), 503

    try:
        business = db.session.execute(
            text("""
                SELECT id
                FROM businesses
                WHERE id = :business_id AND is_active = TRUE
                FOR UPDATE
            """),
            {"business_id": business_id},
        ).first()
        if not business:
            db.session.rollback()
            return jsonify({"status": "error", "message": "Business not found"}), 404

        db.session.execute(
            text("""
                UPDATE businesses
                SET queue_paused = TRUE,
                    updated_at = NOW()
                WHERE id = :business_id
            """),
            {"business_id": business_id},
        )
        db.session.commit()

        return jsonify({
            "status": "success",
            "message": "Queue paused",
            "business_id": business_id,
            "queue_paused": True,
        }), 200

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Pause queue failed")
        return jsonify({"status": "error", "message": "Unable to pause queue"}), 500


@queue_bp.route("/businesses/<business_id>/queue/resume", methods=["POST"])
@token_required
def resume_queue(business_id):
    if not _is_uuid(business_id):
        return jsonify({"status": "error", "message": "Business not found"}), 404

    user_id = g.current_user["id"]
    if business_id not in accessible_business_ids(user_id):
        return jsonify({"status": "error", "message": "Business not found"}), 404

    if not _queue_paused_column_exists():
        return jsonify({
            "status": "error",
            "message": "Queue resume requires database migration 001_add_queue_paused_to_businesses.sql",
        }), 503

    try:
        business = db.session.execute(
            text("""
                SELECT id
                FROM businesses
                WHERE id = :business_id AND is_active = TRUE
                FOR UPDATE
            """),
            {"business_id": business_id},
        ).first()
        if not business:
            db.session.rollback()
            return jsonify({"status": "error", "message": "Business not found"}), 404

        db.session.execute(
            text("""
                UPDATE businesses
                SET queue_paused = FALSE,
                    updated_at = NOW()
                WHERE id = :business_id
            """),
            {"business_id": business_id},
        )
        db.session.commit()

        return jsonify({
            "status": "success",
            "message": "Queue resumed",
            "business_id": business_id,
            "queue_paused": False,
        }), 200

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Resume queue failed")
        return jsonify({"status": "error", "message": "Unable to resume queue"}), 500
