from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash
from sqlalchemy import text
from app import create_app
from app.extensions import db

MARKER = "DEMO-GENERATED:QUEUELESS-PRODUCTION-V1"

BUSINESSES = [
    ("Pioneer Community Bank", "Bank",
     "Banking and financial services"),
    ("Maple Row Market", "Retail",
     "Grocery and daily essentials"),
    ("BrightPath Computer Service", "Technology",
     "Computer repair and technical support"),
    ("CivicSquare Service Centre", "Public Services",
     "Document and citizen services"),
    ("Northstar Tablehouse", "Restaurant",
     "Restaurant and dining services"),
    ("Harborview Family Clinic", "Clinic",
     "General healthcare services"),
    ("Juniper & Co. Salon", "Salon",
     "Hair and beauty services"),
    ("Cedarline Auto Care", "Automotive",
     "Vehicle servicing and maintenance"),
]

SERVICES = {
    "Pioneer Community Bank": [
        ("Cash Deposit", 10, 0),
        ("Cash Withdrawal", 10, 0),
        ("Account Assistance", 20, 0),
        ("Cheque Services", 15, 0),
    ],
    "Maple Row Market": [
        ("General Checkout", 10, 0),
        ("Returns and Exchanges", 15, 0),
        ("Customer Assistance", 10, 0),
        ("Bulk Order Pickup", 20, 0),
    ],
    "BrightPath Computer Service": [
        ("Laptop Diagnosis", 20, 199),
        ("Software Support", 30, 299),
        ("Hardware Repair", 45, 599),
        ("System Installation", 40, 499),
    ],
    "CivicSquare Service Centre": [
        ("Document Verification", 15, 0),
        ("Application Assistance", 20, 0),
        ("Certificate Collection", 10, 0),
        ("Citizen Help Desk", 15, 0),
    ],
    "Northstar Tablehouse": [
        ("Table Reservation", 10, 0),
        ("Takeaway Order", 15, 0),
        ("Billing Assistance", 10, 0),
        ("Customer Support", 10, 0),
    ],
    "Harborview Family Clinic": [
        ("General Consultation", 20, 300),
        ("Follow-up Consultation", 10, 150),
        ("Blood Pressure Check", 10, 50),
        ("Health Checkup", 30, 500),
    ],
    "Juniper & Co. Salon": [
        ("Haircut", 30, 250),
        ("Hair Styling", 30, 350),
        ("Hair Wash", 15, 150),
        ("Grooming Service", 20, 200),
    ],
    "Cedarline Auto Care": [
        ("Vehicle Inspection", 20, 250),
        ("Oil Change", 30, 700),
        ("General Servicing", 60, 1500),
        ("Vehicle Cleaning", 30, 400),
    ],
}

CUSTOMERS = [
    ("Demo Customer One", "9000000001"),
    ("Demo Customer Two", "9000000002"),
    ("Demo Customer Three", "9000000003"),
    ("Demo Customer Four", "9000000004"),
]


def run():
    app = create_app()

    with app.app_context():
        engine = db.engine
        host = engine.url.host

        if not host or "supabase" not in host:
            raise RuntimeError(
                "Safety stop: configured database is not recognized "
                "as the intended Supabase database."
            )

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        queue_date = now.date()
        first_slot = now + timedelta(minutes=5)

        totals = {
            "businesses_created": 0,
            "services_created": 0,
            "customers_created": 0,
            "appointments_created": 0,
            "queue_tokens_created": 0,
        }

        with engine.begin() as conn:
            # Use the existing business owner; do not create or alter users.
            owner = conn.execute(text("""
                SELECT owner_id
                FROM businesses
                WHERE business_name = 'Vinay Clinic'
                LIMIT 1
            """)).scalar_one_or_none()

            if not owner:
                raise RuntimeError(
                    "Safety stop: could not identify the existing business owner."
                )

            print("Production database:", host)
            print("Existing owner account will be reused.")
            print("No existing business or user will be modified.")

            for business_index, (name, kind, description) in enumerate(
                BUSINESSES, start=1
            ):
                marker_description = f"{MARKER} | {description}"

                existing = conn.execute(text("""
                    SELECT id, description
                    FROM businesses
                    WHERE business_name = :name
                    FOR UPDATE
                """), {"name": name}).mappings().all()

                marked = [
                    row for row in existing
                    if row["description"]
                    and row["description"].startswith(MARKER)
                ]

                if existing and not marked:
                    raise RuntimeError(
                        f"Safety stop: business name already exists: {name}"
                    )

                if len(marked) > 1:
                    raise RuntimeError(
                        f"Safety stop: duplicate demo businesses found: {name}"
                    )

                if marked:
                    business_id = marked[0]["id"]
                else:
                    business_id = conn.execute(text("""
                        INSERT INTO businesses (
                            owner_id, business_name, business_type,
                            description, address, phone, email,
                            opening_time, closing_time, average_service_time,
                            is_active, queue_paused, working_days, timezone
                        ) VALUES (
                            :owner, :name, :kind,
                            :description, 'Demo Location, Bengaluru, India',
                            '9000000000', :email,
                            '00:00', '23:59', 15,
                            TRUE, FALSE, ARRAY[0,1,2,3,4,5,6],
                            'Asia/Kolkata'
                        )
                        RETURNING id
                    """), {
                        "owner": owner,
                        "name": name,
                        "kind": kind,
                        "description": marker_description,
                        "email": f"demo-{business_index}@queueless.local",
                    }).scalar_one()

                    totals["businesses_created"] += 1

                service_ids = []

                for service_name, duration, price in SERVICES[name]:
                    service = conn.execute(text("""
                        SELECT id
                        FROM services
                        WHERE business_id = :business
                          AND service_name = :service
                        FOR UPDATE
                    """), {
                        "business": business_id,
                        "service": service_name,
                    }).scalar_one_or_none()

                    if service is None:
                        service = conn.execute(text("""
                            INSERT INTO services (
                                business_id, service_name, description,
                                duration_minutes, price, is_active
                            ) VALUES (
                                :business, :service, :description,
                                :duration, :price, TRUE
                            )
                            RETURNING id
                        """), {
                            "business": business_id,
                            "service": service_name,
                            "description": f"{MARKER} service",
                            "duration": duration,
                            "price": price,
                        }).scalar_one()

                        totals["services_created"] += 1

                    service_ids.append(service)

                for customer_index, (customer_name, phone) in enumerate(
                    CUSTOMERS, start=1
                ):
                    email = (
                        f"demo-ql-{business_index}-{customer_index}"
                        "@queueless.local"
                    )
                    customer = conn.execute(text("""
                        SELECT id, full_name
                        FROM customers
                        WHERE email = :email
                        FOR UPDATE
                    """), {"email": email}).mappings().first()

                    if customer:
                        if customer["full_name"] != customer_name:
                            raise RuntimeError(
                                f"Safety stop: customer email conflict: {email}"
                            )
                        customer_id = customer["id"]
                    else:
                        customer_id = conn.execute(text("""
                            INSERT INTO customers (
                                full_name, email, phone,
                                password_hash, is_active
                            ) VALUES (
                                :name, :email, :phone, :password, TRUE
                            )
                            RETURNING id
                        """), {
                            "name": customer_name,
                            "email": email,
                            "phone": phone,
                            "password": generate_password_hash(
                                "DEMO-ACCOUNT-NOT-FOR-LOGIN-"
                                + email
                            ),
                        }).scalar_one()

                        totals["customers_created"] += 1

                    appointment_marker = (
                        f"{MARKER}:{business_index}:{customer_index}"
                    )

                    appointment = conn.execute(text("""
                        SELECT id, scheduled_at, service_id
                        FROM appointments
                        WHERE notes = :marker
                        FOR UPDATE
                    """), {"marker": appointment_marker}).mappings().first()

                    service_id = service_ids[(customer_index - 1) % 4]

                    if appointment:
                        appointment_id = appointment["id"]
                        scheduled_at = appointment["scheduled_at"]
                    else:
                        scheduled_at = (
                            first_slot
                            + timedelta(minutes=(customer_index - 1) * 15)
                        )

                        appointment_id = conn.execute(text("""
                            INSERT INTO appointments (
                                business_id, service_id,
                                customer_name, customer_phone,
                                customer_email, customer_id,
                                scheduled_at, status, notes
                            ) VALUES (
                                :business, :service, :name, :phone,
                                :email, :customer, :scheduled,
                                'confirmed', :marker
                            )
                            RETURNING id
                        """), {
                            "business": business_id,
                            "service": service_id,
                            "name": customer_name,
                            "phone": phone,
                            "email": email,
                            "customer": customer_id,
                            "scheduled": scheduled_at,
                            "marker": appointment_marker,
                        }).scalar_one()

                        totals["appointments_created"] += 1

                    token = conn.execute(text("""
                        SELECT id
                        FROM queue_tokens
                        WHERE appointment_id = :appointment
                        FOR UPDATE
                    """), {"appointment": appointment_id}).scalar_one_or_none()

                    if token is None:
                        next_number = conn.execute(text("""
                            SELECT COALESCE(MAX(token_number), 0) + 1
                            FROM queue_tokens
                            WHERE business_id = :business
                              AND queue_date = :queue_date
                        """), {
                            "business": business_id,
                            "queue_date": queue_date,
                        }).scalar_one()

                        tracking_code = (
                            f"DEMO-QL-{business_index:02d}-{customer_index:02d}"
                        )

                        conn.execute(text("""
                            INSERT INTO queue_tokens (
                                business_id, service_id, appointment_id,
                                customer_name, customer_phone, customer_id,
                                token_number, queue_date, tracking_code,
                                status, joined_at
                            ) VALUES (
                                :business, :service, :appointment,
                                :name, :phone, :customer,
                                :number, :queue_date, :tracking,
                                'waiting', :joined
                            )
                        """), {
                            "business": business_id,
                            "service": service_id,
                            "appointment": appointment_id,
                            "name": customer_name,
                            "phone": phone,
                            "customer": customer_id,
                            "number": next_number,
                            "queue_date": queue_date,
                            "tracking": tracking_code,
                            "joined": now,
                        })

                        totals["queue_tokens_created"] += 1

                print(f"Prepared: {name}")

        print("\n========== PRODUCTION SEED COMPLETE ==========")
        for key, value in totals.items():
            print(f"{key}: {value}")

        print("Demo businesses:", len(BUSINESSES))
        print("Expected demo services:", len(BUSINESSES) * 4)
        print("Expected demo customers:", len(BUSINESSES) * 4)
        print("Expected demo appointments:", len(BUSINESSES) * 4)
        print("Expected demo queue entries:", len(BUSINESSES) * 4)
        print("Existing Vinay Clinic was not modified.")


if __name__ == "__main__":
    run()
