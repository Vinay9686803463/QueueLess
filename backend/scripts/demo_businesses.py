
# cspell: disable

import argparse
import sys
from datetime import datetime, time, timezone
from urllib.parse import urlparse

from sqlalchemy import bindparam, text


DEMO_BUSINESSES = (
    {
        "slug": "northstar-tablehouse",
        "name": "Northstar Tablehouse",
        "category": "Restaurant",
        "description": "A fictional neighborhood restaurant for QueueLess demos.",
        "address": "101 Example Way, Demo City",
        "phone": "+1-202-555-0101",
        "services": (
            ("Dine-in", "Table seating and dining service.", 35),
            ("Takeaway", "Order pickup at the counter.", 15),
            ("Table Reservation", "Reservation and seating assistance.", 10),
            ("Dessert Pickup", "Dessert orders for pickup.", 10),
        ),
    },
    {
        "slug": "harborview-family-clinic",
        "name": "Harborview Family Clinic",
        "category": "Hospital/Clinic",
        "description": "A fictional community clinic for QueueLess demos.",
        "address": "202 Sample Avenue, Demo City",
        "phone": "+1-202-555-0102",
        "services": (
            ("General Consultation", "Routine primary care consultation.", 25),
            ("Dental Consultation", "Initial dental assessment.", 30),
            ("Follow-up Visit", "Follow-up care and review.", 15),
            ("Vaccination", "Routine vaccination appointment.", 15),
        ),
    },
    {
        "slug": "juniper-and-co-salon",
        "name": "Juniper & Co. Salon",
        "category": "Salon",
        "description": "A fictional salon studio for QueueLess demos.",
        "address": "303 Fictional Street, Demo City",
        "phone": "+1-202-555-0103",
        "services": (
            ("Haircut", "Cut and finishing service.", 35),
            ("Hair Styling", "Wash, styling, and finishing.", 45),
            ("Color Consultation", "Color planning consultation.", 20),
            ("Facial", "Basic salon facial service.", 40),
        ),
    },
    {
        "slug": "cedarline-auto-care",
        "name": "Cedarline Auto Care",
        "category": "Automobile Service Center",
        "description": "A fictional auto workshop for QueueLess demos.",
        "address": "404 Placeholder Road, Demo City",
        "phone": "+1-202-555-0104",
        "services": (
            ("Oil Change", "Standard oil and filter service.", 30),
            ("Vehicle Inspection", "Routine vehicle safety inspection.", 45),
            ("Tire Service", "Tire check and rotation.", 35),
            ("Battery Check", "Battery and charging system check.", 20),
        ),
    },
    {
        "slug": "pioneer-community-bank",
        "name": "Pioneer Community Bank",
        "category": "Banking Service Center",
        "description": "A fictional community bank branch for QueueLess demos.",
        "address": "505 Demo Boulevard, Demo City",
        "phone": "+1-202-555-0105",
        "services": (
            ("Account Services", "Account maintenance assistance.", 20),
            ("Cashier Service", "Routine teller transaction.", 10),
            ("Loan Consultation", "Loan information consultation.", 35),
            ("Card Support", "Debit and credit card assistance.", 15),
        ),
    },
    {
        "slug": "maple-row-market",
        "name": "Maple Row Market",
        "category": "Retail Store",
        "description": "A fictional retail shop for QueueLess demos.",
        "address": "606 Mockingbird Lane, Demo City",
        "phone": "+1-202-555-0106",
        "services": (
            ("Checkout", "Retail checkout assistance.", 8),
            ("Returns", "Returns and exchange support.", 12),
            ("Product Help", "Product information and assistance.", 15),
            ("Order Pickup", "Collection of online orders.", 10),
        ),
    },
    {
        "slug": "brightpath-computer-service",
        "name": "BrightPath Computer Service",
        "category": "Computer Service Center",
        "description": "A fictional computer repair desk for QueueLess demos.",
        "address": "707 Placeholder Park, Demo City",
        "phone": "+1-202-555-0107",
        "services": (
            ("Diagnostics", "Initial computer hardware diagnostics.", 30),
            ("Software Support", "Operating system and software help.", 25),
            ("Device Repair", "Computer repair intake and service.", 50),
            ("Data Transfer", "Device-to-device data transfer.", 35),
        ),
    },
    {
        "slug": "civicsquare-service-centre",
        "name": "CivicSquare Service Centre",
        "category": "Government Service Center",
        "description": "A fictional public service desk for QueueLess demos.",
        "address": "808 Example Plaza, Demo City",
        "phone": "+1-202-555-0108",
        "services": (
            ("Document Services", "Document intake and processing.", 20),
            ("Permit Consultation", "General permit information.", 25),
            ("Records Request", "Public records request assistance.", 15),
            ("Benefits Guidance", "Initial benefits information session.", 30),
        ),
    },
)


DEMO_CUSTOMER_FIRST_NAMES = (
    "Avery", "Jordan", "Morgan", "Riley", "Casey", "Quinn",
    "Taylor", "Cameron", "Skyler", "Reese", "Emerson", "Rowan",
)

DEMO_CUSTOMER_LAST_NAMES = (
    "Bennett", "Rivera", "Chen", "Thompson", "Patel", "Foster",
    "Brooks", "Lee", "Walker", "Carter", "Kim", "Ellis",
)

DEMO_QUEUE_SIZE = 12
DEMO_BUSINESS_EMAIL_DOMAIN = "queueless.invalid"

DEMO_OPENING_TIME = time(9, 0)
DEMO_CLOSING_TIME = time(17, 0)
DEMO_TIMEZONE = "Asia/Kolkata"

DEMO_SERVICE_DESCRIPTION_PREFIX = "[QueueLess DEMO] "
DEMO_TRACKING_PREFIX = "DEMO-"


def demo_business_email(slug):
    return f"demo+{slug}@{DEMO_BUSINESS_EMAIL_DOMAIN}"


def is_safe_demo_target(config):
    if str(config.get("ENV", "")).lower() != "development":
        return False

    if not config.get("QUEUELESS_ENABLE_DEMO_DATA", False):
        return False

    database_host = urlparse(
        config.get("SQLALCHEMY_DATABASE_URI", "")
    ).hostname

    return database_host in {"localhost", "127.0.0.1", "::1"}


def _queue_tracking_code(business_id, queue_date, number):
    return (
        f"{DEMO_TRACKING_PREFIX}{business_id.replace('-', '')}-"
        f"{queue_date:%Y%m%d}-{number:02d}"
    )


def _demo_customer_name(business_index, queue_position):
    name_index = business_index * DEMO_QUEUE_SIZE + queue_position - 1

    first_name = DEMO_CUSTOMER_FIRST_NAMES[
        name_index // len(DEMO_CUSTOMER_LAST_NAMES)
    ]

    last_name = DEMO_CUSTOMER_LAST_NAMES[
        name_index % len(DEMO_CUSTOMER_LAST_NAMES)
    ]

    return f"DEMO · {first_name} {last_name}"


def _get_or_create_business(db, owner_id, demo_business):
    marker_email = demo_business_email(demo_business["slug"])

    existing = db.session.execute(
        text("""
            SELECT id::text AS id,
                   owner_id::text AS owner_id,
                   business_name,
                   business_type,
                   is_active,
                   opening_time,
                   closing_time
            FROM businesses
            WHERE lower(email) = :email
            FOR UPDATE
        """),
        {"email": marker_email},
    ).mappings().all()

    if len(existing) > 1:
        raise RuntimeError(
            f"Multiple businesses use demo marker {marker_email}"
        )

    if existing:
        business = existing[0]

        if (
            str(business["owner_id"]) != str(owner_id)
            or business["business_name"] != f"DEMO · {demo_business['name']}"
            or business["business_type"] != demo_business["category"]
        ):
            raise RuntimeError(
                f"Demo business marker conflict for {demo_business['name']}; "
                "no existing business was changed"
            )

        if not business["is_active"]:
            raise RuntimeError(
                f"Demo business {demo_business['name']} is inactive; "
                "no existing business was changed"
            )

        # Preserve configured business hours.
        # Fill missing hours and set the demo timezone to India.
        db.session.execute(
            text("""
                UPDATE businesses
                SET opening_time = COALESCE(
                        opening_time,
                        :opening_time
                    ),
                    closing_time = COALESCE(
                        closing_time,
                        :closing_time
                    ),
                    timezone = :timezone
                WHERE id = :business_id
                  AND (
                      opening_time IS NULL
                      OR closing_time IS NULL
                      OR timezone IS DISTINCT FROM :timezone
                  )
            """),
            {
                "business_id": business["id"],
                "opening_time": DEMO_OPENING_TIME,
                "closing_time": DEMO_CLOSING_TIME,
                "timezone": DEMO_TIMEZONE,
            },
        )

        return business["id"], False

    business_id = db.session.execute(
        text("""
            INSERT INTO businesses (
                owner_id,
                business_name,
                business_type,
                description,
                address,
                phone,
                email,
                average_service_time,
                opening_time,
                closing_time,
                timezone,
                is_active
            )
            VALUES (
                :owner_id,
                :business_name,
                :business_type,
                :description,
                :address,
                :phone,
                :email,
                :average_service_time,
                :opening_time,
                :closing_time,
                :timezone,
                TRUE
            )
            RETURNING id::text
        """),
        {
            "owner_id": owner_id,
            "business_name": f"DEMO · {demo_business['name']}",
            "business_type": demo_business["category"],
            "description": demo_business["description"],
            "address": demo_business["address"],
            "phone": demo_business["phone"],
            "email": marker_email,
            "average_service_time": min(
                service[2] for service in demo_business["services"]
            ),
            "opening_time": DEMO_OPENING_TIME,
            "closing_time": DEMO_CLOSING_TIME,
            "timezone": DEMO_TIMEZONE,
        },
    ).scalar_one()

    return business_id, True


def _ensure_demo_services(db, business_id, demo_business):
    created = 0

    for service_name, description, duration in demo_business["services"]:
        existing = db.session.execute(
            text("""
                SELECT id::text AS id, description
                FROM services
                WHERE business_id = :business_id
                  AND service_name = :service_name
                FOR UPDATE
            """),
            {
                "business_id": business_id,
                "service_name": service_name,
            },
        ).mappings().first()

        if existing:
            if not (existing["description"] or "").startswith(
                DEMO_SERVICE_DESCRIPTION_PREFIX
            ):
                raise RuntimeError(
                    f"Service name conflict for {service_name}; "
                    "no existing service was changed"
                )

            continue

        db.session.execute(
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
                    0,
                    TRUE
                )
            """),
            {
                "business_id": business_id,
                "service_name": service_name,
                "description": DEMO_SERVICE_DESCRIPTION_PREFIX + description,
                "duration_minutes": duration,
            },
        )

        created += 1

    return created


def _ensure_demo_queue(
    db,
    business_id,
    service_ids,
    queue_date,
    business_index,
):
    created = 0

    for index in range(1, DEMO_QUEUE_SIZE + 1):
        tracking_code = _queue_tracking_code(
            business_id,
            queue_date,
            index,
        )

        existing = db.session.execute(
            text("""
                SELECT id
                FROM queue_tokens
                WHERE tracking_code = :tracking_code
                  AND business_id = :business_id
                FOR UPDATE
            """),
            {
                "tracking_code": tracking_code,
                "business_id": business_id,
            },
        ).first()

        if existing:
            linked = db.session.execute(
                text("""
                    SELECT customer_id IS NOT NULL
                           OR appointment_id IS NOT NULL
                    FROM queue_tokens
                    WHERE tracking_code = :tracking_code
                """),
                {"tracking_code": tracking_code},
            ).scalar()

            if linked:
                raise RuntimeError(
                    "A reserved demo queue marker is linked to a customer "
                    "or appointment; cleanup or seeding stopped "
                    "without changing it"
                )

            continue

        token_number = _generate_token_number(
            db,
            business_id,
            queue_date,
        )

        service_id = service_ids[(index - 1) % len(service_ids)]
        minutes_ago = index * 9

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
                "service_id": service_id,
                "customer_name": _demo_customer_name(
                    business_index,
                    index,
                ),
                "customer_phone": f"+1-202-555-01{index:02d}",
                "token_number": token_number,
                "queue_date": queue_date,
                "tracking_code": tracking_code,
                "minutes_ago": minutes_ago,
            },
        )

        created += 1

    return created


def _generate_token_number(db, business_id, queue_date):
    db.session.execute(
        text("""
            INSERT INTO queue_daily_counters (
                business_id,
                queue_date,
                next_token_number
            )
            VALUES (
                :business_id,
                :queue_date,
                COALESCE((
                    SELECT MAX(token_number) + 1
                    FROM queue_tokens
                    WHERE business_id = :business_id
                      AND queue_date = :queue_date
                ), 1)
            )
            ON CONFLICT (business_id, queue_date)
            DO UPDATE SET next_token_number = GREATEST(
                queue_daily_counters.next_token_number,
                EXCLUDED.next_token_number
            )
        """),
        {
            "business_id": business_id,
            "queue_date": queue_date,
        },
    )

    token_number = db.session.execute(
        text("""
            SELECT next_token_number
            FROM queue_daily_counters
            WHERE business_id = :business_id
              AND queue_date = :queue_date
            FOR UPDATE
        """),
        {
            "business_id": business_id,
            "queue_date": queue_date,
        },
    ).scalar_one()

    db.session.execute(
        text("""
            UPDATE queue_daily_counters
            SET next_token_number = next_token_number + 1
            WHERE business_id = :business_id
              AND queue_date = :queue_date
        """),
        {
            "business_id": business_id,
            "queue_date": queue_date,
        },
    )

    return token_number


def seed_demo_businesses(db, owner_email):
    owner = db.session.execute(
        text("""
            SELECT id::text AS id
            FROM users
            WHERE lower(email) = :email
              AND is_active = TRUE
            FOR UPDATE
        """),
        {"email": owner_email.strip().lower()},
    ).mappings().all()

    if len(owner) != 1:
        raise RuntimeError(
            "The specified active admin account was not found uniquely"
        )

    owner_id = owner[0]["id"]
    queue_date = datetime.now(timezone.utc).date()

    result = {
        "businesses_created": 0,
        "services_created": 0,
        "queue_entries_created": 0,
    }

    for business_index, demo_business in enumerate(DEMO_BUSINESSES):
        business_id, business_created = _get_or_create_business(
            db,
            owner_id,
            demo_business,
        )

        result["businesses_created"] += int(business_created)

        expected_names = {
            service[0] for service in demo_business["services"]
        }

        result["services_created"] += _ensure_demo_services(
            db,
            business_id,
            demo_business,
        )

        service_rows = db.session.execute(
            text("""
                SELECT id::text AS id, service_name, description
                FROM services
                WHERE business_id = :business_id
                  AND service_name IN :service_names
                ORDER BY service_name
            """).bindparams(
                bindparam("service_names", expanding=True)
            ),
            {
                "business_id": business_id,
                "service_names": tuple(expected_names),
            },
        ).mappings().all()

        service_map = {
            row["service_name"]: row["id"]
            for row in service_rows
            if (row["description"] or "").startswith(
                DEMO_SERVICE_DESCRIPTION_PREFIX
            )
        }

        if len(service_map) != len(expected_names):
            raise RuntimeError(
                f"Demo service catalog is incomplete for "
                f"{demo_business['name']}"
            )

        result["queue_entries_created"] += _ensure_demo_queue(
            db,
            business_id,
            [
                service_map[service_name]
                for service_name, _, _ in demo_business["services"]
            ],
            queue_date,
            business_index,
        )

    return result


def cleanup_demo_businesses(db, owner_email):
    owner = db.session.execute(
        text("""
            SELECT id::text AS id
            FROM users
            WHERE lower(email) = :email
              AND is_active = TRUE
            FOR UPDATE
        """),
        {"email": owner_email.strip().lower()},
    ).mappings().all()

    if len(owner) != 1:
        raise RuntimeError(
            "The specified active admin account was not found uniquely"
        )

    owner_id = owner[0]["id"]

    totals = {
        "queue_entries_removed": 0,
        "services_removed": 0,
        "businesses_removed": 0,
        "businesses_preserved": 0,
    }

    for demo_business in DEMO_BUSINESSES:
        marker_email = demo_business_email(demo_business["slug"])

        business = db.session.execute(
            text("""
                SELECT id::text AS id
                FROM businesses
                WHERE owner_id = :owner_id
                  AND lower(email) = :email
                  AND business_name = :business_name
                  AND business_type = :business_type
                FOR UPDATE
            """),
            {
                "owner_id": owner_id,
                "email": marker_email,
                "business_name": f"DEMO · {demo_business['name']}",
                "business_type": demo_business["category"],
            },
        ).mappings().first()

        if not business:
            continue

        business_id = business["id"]

        prefix = (
            f"{DEMO_TRACKING_PREFIX}"
            f"{business_id.replace('-', '')}-%"
        )

        removed = db.session.execute(
            text("""
                DELETE FROM queue_tokens
                WHERE business_id = :business_id
                  AND tracking_code LIKE :tracking_prefix
                  AND customer_id IS NULL
                  AND appointment_id IS NULL
                RETURNING id
            """),
            {
                "business_id": business_id,
                "tracking_prefix": prefix,
            },
        ).fetchall()

        totals["queue_entries_removed"] += len(removed)

        service_names = tuple(
            service[0] for service in demo_business["services"]
        )

        service_result = db.session.execute(
            text("""
                DELETE FROM services s
                WHERE s.business_id = :business_id
                  AND s.service_name IN :service_names
                  AND s.description LIKE :description_prefix
                  AND NOT EXISTS (
                      SELECT 1
                      FROM queue_tokens qt
                      WHERE qt.service_id = s.id
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM appointments a
                      WHERE a.service_id = s.id
                  )
                RETURNING s.id
            """).bindparams(
                bindparam("service_names", expanding=True)
            ),
            {
                "business_id": business_id,
                "service_names": service_names,
                "description_prefix": (
                    DEMO_SERVICE_DESCRIPTION_PREFIX + "%"
                ),
            },
        ).fetchall()

        totals["services_removed"] += len(service_result)

        can_remove_business = db.session.execute(
            text("""
                SELECT
                    NOT EXISTS (
                        SELECT 1
                        FROM queue_tokens
                        WHERE business_id = :business_id
                    )
                    AND NOT EXISTS (
                        SELECT 1
                        FROM appointments
                        WHERE business_id = :business_id
                    )
                    AND NOT EXISTS (
                        SELECT 1
                        FROM services
                        WHERE business_id = :business_id
                    )
                    AND NOT EXISTS (
                        SELECT 1
                        FROM business_staff
                        WHERE business_id = :business_id
                    )
            """),
            {"business_id": business_id},
        ).scalar_one()

        if can_remove_business:
            db.session.execute(
                text("""
                    DELETE FROM businesses
                    WHERE id = :business_id
                      AND owner_id = :owner_id
                """),
                {
                    "business_id": business_id,
                    "owner_id": owner_id,
                },
            )

            totals["businesses_removed"] += 1
        else:
            totals["businesses_preserved"] += 1

    return totals


def _print_preview():
    print(
        "QueueLess fictional demo data preview "
        "(no database connection):"
    )

    for business in DEMO_BUSINESSES:
        print(
            f"- DEMO · {business['name']} ({business['category']}): "
            f"{len(business['services'])} services, "
            f"{DEMO_QUEUE_SIZE} queue entries"
        )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Seed or clean QueueLess demo businesses "
            "in a local development database."
        )
    )

    parser.add_argument(
        "--owner-email",
        help="Existing active admin email to own demo businesses",
    )

    parser.add_argument(
        "--cleanup",
        action="store_true",
        help=(
            "Remove only marked demo queue rows and unreferenced "
            "demo services/businesses"
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "List planned demo data without loading configuration "
            "or connecting to a database"
        ),
    )

    args = parser.parse_args(argv)

    if args.dry_run:
        _print_preview()
        return 0

    if not args.owner_email:
        parser.error(
            "--owner-email is required unless --dry-run is used"
        )

    from config import Config

    if not is_safe_demo_target(Config.__dict__):
        print(
            "Refusing demo-data writes: require FLASK_ENV=development, "
            "QUEUELESS_ENABLE_DEMO_DATA=true, and a localhost database.",
            file=sys.stderr,
        )
        return 2

    from app import create_app
    from app.extensions import db

    app = create_app()

    with app.app_context():
        try:
            result = (
                cleanup_demo_businesses(db, args.owner_email)
                if args.cleanup
                else seed_demo_businesses(db, args.owner_email)
            )

            db.session.commit()

        except Exception as error:
            db.session.rollback()

            print(
                f"Demo data operation failed ({type(error).__name__}); "
                "the transaction was rolled back.",
                file=sys.stderr,
            )

            return 1

    print("Demo data operation completed:")

    for key, value in result.items():
        print(f"- {key.replace('_', ' ')}: {value}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
