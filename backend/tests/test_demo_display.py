from app.utils.display import (
    DEMO_MARKER,
    clean_demo_service_description,
)


def test_removes_marker_and_keeps_real_description():
    value = f"{DEMO_MARKER} | Free initial consultation"
    assert clean_demo_service_description(value) == "Free initial consultation"


def test_hides_marker_only_description():
    assert clean_demo_service_description(DEMO_MARKER) is None


def test_hides_seeded_generic_service_description():
    assert clean_demo_service_description(f"{DEMO_MARKER} service") is None


def test_preserves_normal_description():
    value = "Free consultation for new customers"
    assert clean_demo_service_description(value) == value


def test_preserves_none():
    assert clean_demo_service_description(None) is None


def test_preserves_non_string_values():
    assert clean_demo_service_description(123) == 123
