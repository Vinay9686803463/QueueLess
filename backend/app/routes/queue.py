import random
import secrets
import uuid as uuid_lib
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import Blueprint, request, jsonify, g, current_app
from sqlalchemy import bindparam, text
from sqlalchemy.exc import IntegrityError

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
            {"business_id": business_id, "queue_date": today},
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
            "queue_date": today.isoformat(),
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

        services = db.session.execute(
            text("""
                SELECT id::text AS id
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

        tracking_codes = {
            f"{DEMO_TRACKING_PREFIX}{business_id.replace('-', '')}-{today:%Y%m%d}-{number:02d}"
            for number in range(1, DEMO_QUEUE_SIZE + 1)
        }
        existing_codes = set(db.session.execute(
            text("""
                SELECT tracking_code
                FROM queue_tokens
                WHERE business_id = :business_id
                  AND queue_date = :queue_date
                  AND tracking_code IN :tracking_codes
                  AND customer_id IS NULL
                  AND appointment_id IS NULL
                FOR UPDATE
            """).bindparams(bindparam("tracking_codes", expanding=True)),
            {
                "business_id": business_id,
                "queue_date": today,
                "tracking_codes": tuple(tracking_codes),
            },
        ).scalars().all())

        names = random.SystemRandom().sample(
            DEMO_CUSTOMER_NAMES, DEMO_QUEUE_SIZE
        )
        created = 0
        for index in range(1, DEMO_QUEUE_SIZE + 1):
            tracking_code = (
                f"{DEMO_TRACKING_PREFIX}{business_id.replace('-', '')}-"
                f"{today:%Y%m%d}-{index:02d}"
            )
            if tracking_code in existing_codes:
                continue

            token_number = generate_token_number(business_id, today)
            db.session.execute(
                text("""
                    INSERT INTO queue_tokens (
                        business_id,
                        service_id,
                        customer_name,
                        customer_phone,
                        token_number,
                        queue_date,
                        tracking_code,
                        status,
                        joined_at,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        :business_id,
                        :service_id,
                        :customer_name,
                        :customer_phone,
                        :token_number,
                        :queue_date,
                        :tracking_code,
                        'waiting',
                        NOW() - make_interval(mins => :minutes_ago),
                        NOW() - make_interval(mins => :minutes_ago),
                        NOW() - make_interval(mins => :minutes_ago)
                    )
                """),
                {
                    "business_id": business_id,
                    "service_id": random.choice(services)["id"],
                    "customer_name": f"DEMO · {names[index - 1]}",
                    "customer_phone": f"555-01{index:02d}",
                    "token_number": token_number,
                    "queue_date": today,
                    "tracking_code": tracking_code,
                    "minutes_ago": random.randint(5, 180),
                },
            )
            created += 1

        db.session.commit()
        return jsonify({
            "status": "success",
            "created": created,
            "total_demo_entries": DEMO_QUEUE_SIZE,
            "message": (
                f"Created {created} demo queue entries."
                if created
                else "Demo queue entries already exist for today."
            ),
        }), 201 if created else 200
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
        result = db.session.execute(
            text("""
                DELETE FROM queue_tokens
                WHERE business_id = :business_id
                  AND tracking_code LIKE :demo_prefix
                  AND customer_id IS NULL
                  AND appointment_id IS NULL
                RETURNING id
            """),
            {
                "business_id": business_id,
                "demo_prefix": f"{DEMO_TRACKING_PREFIX}{business_id.replace('-', '')}-%",
            },
        )
        removed = len(result.fetchall())
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
