import sys
from datetime import date
from types import ModuleType, SimpleNamespace

from scripts.demo_businesses import (
    DEMO_BUSINESSES,
    DEMO_SERVICE_DESCRIPTION_PREFIX,
    DEMO_QUEUE_SIZE,
    _ensure_demo_queue,
    _ensure_demo_services,
    _get_or_create_business,
    _demo_customer_name,
    demo_business_email,
    is_safe_demo_target,
    main,
)


def test_demo_catalog_has_eight_marked_businesses_and_four_services_each():
    assert len(DEMO_BUSINESSES) == 8
    assert all(len(business["services"]) == 4 for business in DEMO_BUSINESSES)
    assert len({
        demo_business_email(business["slug"])
        for business in DEMO_BUSINESSES
    }) == 8


def test_demo_customer_names_are_unique_across_all_businesses():
    names = {
        _demo_customer_name(business_index, queue_position)
        for business_index in range(len(DEMO_BUSINESSES))
        for queue_position in range(1, DEMO_QUEUE_SIZE + 1)
    }

    assert len(names) == len(DEMO_BUSINESSES) * DEMO_QUEUE_SIZE
    assert all(name.startswith("DEMO · ") for name in names)


def test_demo_business_seed_refuses_non_local_or_unapproved_targets():
    config = {
        "ENV": "development",
        "QUEUELESS_ENABLE_DEMO_DATA": True,
        "SQLALCHEMY_DATABASE_URI": "postgresql://localhost/queueless",
    }
    assert is_safe_demo_target(config)

    config["SQLALCHEMY_DATABASE_URI"] = "postgresql://db.example/queueless"
    assert not is_safe_demo_target(config)

    config["SQLALCHEMY_DATABASE_URI"] = "postgresql://localhost/queueless"
    config["ENV"] = "production"
    assert not is_safe_demo_target(config)

    config["ENV"] = "development"
    config["QUEUELESS_ENABLE_DEMO_DATA"] = False
    assert not is_safe_demo_target(config)


class ExistingRecordResult:
    def __init__(self, *, mappings=None, row=None, scalar=None):
        self._mappings = mappings
        self._row = row
        self._scalar = scalar

    def mappings(self):
        return self

    def all(self):
        return self._mappings or []

    def first(self):
        return self._row

    def scalar(self):
        return self._scalar


class ExistingDemoDb:
    def __init__(self, business, services):
        self.business = business
        self.services = services
        self.statements = []

    class Session:
        def __init__(self, outer):
            self.outer = outer

        def execute(self, statement, params=None):
            sql = str(statement)
            self.outer.statements.append(sql)

            if "FROM businesses" in sql and "lower(email)" in sql:
                return ExistingRecordResult(mappings=[self.outer.business])
            if "UPDATE businesses" in sql:
                self.outer.business["opening_time"] = (
                    self.outer.business.get("opening_time")
                    or params["opening_time"]
                )
                self.outer.business["closing_time"] = (
                    self.outer.business.get("closing_time")
                    or params["closing_time"]
                )
                return ExistingRecordResult()
            if "FROM services" in sql and "service_name = :service_name" in sql:
                service = self.outer.services[params["service_name"]]
                return ExistingRecordResult(row=service)
            if "FROM services" in sql and "service_name IN" in sql:
                return ExistingRecordResult(mappings=[
                    self.outer.services[name]
                    for name in params["service_names"]
                ])
            if "SELECT id" in sql and "FROM queue_tokens" in sql:
                return ExistingRecordResult(row=("existing-demo-entry",))
            if "SELECT customer_id IS NOT NULL" in sql:
                return ExistingRecordResult(scalar=False)
            raise AssertionError(f"Unexpected seed SQL: {sql}")

    @property
    def session(self):
        return self.Session(self)


def test_seed_helpers_leave_existing_demo_records_unchanged():
    business_definition = DEMO_BUSINESSES[0]
    services = {
        name: {
            "id": f"service-{index}",
            "description": DEMO_SERVICE_DESCRIPTION_PREFIX + description,
        }
        for index, (name, description, _) in enumerate(
            business_definition["services"]
        )
    }
    business = {
        "id": "business-existing",
        "owner_id": "owner-existing",
        "business_name": f"DEMO · {business_definition['name']}",
        "business_type": business_definition["category"],
        "is_active": True,
    }
    db = ExistingDemoDb(business, services)

    business_id, business_created = _get_or_create_business(
        db, "owner-existing", business_definition
    )
    services_created = _ensure_demo_services(
        db, business_id, business_definition
    )
    service_ids = [
        services[name]["id"]
        for name, _, _ in business_definition["services"]
    ]
    queue_date = date(2026, 11, 14)
    queue_created = _ensure_demo_queue(
        db, business_id, service_ids, queue_date, 0
    )
    repeated_business_id, repeated_business_created = _get_or_create_business(
        db, "owner-existing", business_definition
    )
    repeated_services_created = _ensure_demo_services(
        db, repeated_business_id, business_definition
    )
    repeated_queue_created = _ensure_demo_queue(
        db, repeated_business_id, service_ids, queue_date, 0
    )

    assert business_id == "business-existing"
    assert not business_created
    assert repeated_business_id == business_id
    assert not repeated_business_created
    assert services_created == 0
    assert repeated_services_created == 0
    assert queue_created == 0
    assert repeated_queue_created == 0
    assert str(business["opening_time"]) == "09:00:00"
    assert str(business["closing_time"]) == "17:00:00"
    assert any("UPDATE businesses" in statement for statement in db.statements)
    assert not any("INSERT INTO" in statement for statement in db.statements)


def test_seed_cli_rolls_back_and_reports_failure_without_exception_details(
    monkeypatch, capsys
):
    class FakeSession:
        def __init__(self):
            self.rollback_count = 0

        def rollback(self):
            self.rollback_count += 1

        def commit(self):
            raise AssertionError("A failed seed must not commit")

    class FakeApp:
        class AppContext:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

        def app_context(self):
            return self.AppContext()

    session = FakeSession()
    fake_db = SimpleNamespace(session=session)
    fake_app_module = ModuleType("app")
    fake_app_module.create_app = FakeApp
    fake_extensions_module = ModuleType("app.extensions")
    fake_extensions_module.db = fake_db
    monkeypatch.setitem(
        sys.modules, "config", SimpleNamespace(Config=SimpleNamespace())
    )
    monkeypatch.setitem(sys.modules, "app", fake_app_module)
    monkeypatch.setitem(sys.modules, "app.extensions", fake_extensions_module)
    monkeypatch.setattr(
        "scripts.demo_businesses.is_safe_demo_target", lambda config: True
    )
    monkeypatch.setattr(
        "scripts.demo_businesses.seed_demo_businesses",
        lambda db, email: (_ for _ in ()).throw(
            RuntimeError("DATABASE_URL=secret-password")
        ),
    )

    result = main(["--owner-email", "admin@example.invalid"])

    captured = capsys.readouterr()
    assert result == 1
    assert session.rollback_count == 1
    assert "Demo data operation failed (RuntimeError)" in captured.err
    assert "rolled back" in captured.err
    assert "secret-password" not in captured.err
