from scripts.demo_businesses import (
    DEMO_BUSINESSES,
    DEMO_QUEUE_SIZE,
    _demo_customer_name,
    demo_business_email,
    is_safe_demo_target,
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
