"""Safe display-value cleanup for QueueLess-generated demo metadata."""

DEMO_MARKER = "DEMO-GENERATED:QUEUELESS-PRODUCTION-V1"


def clean_demo_service_description(value):
    """Hide internal demo markers without changing ordinary descriptions."""
    if not isinstance(value, str):
        return value

    value = value.strip()
    if not value.startswith(DEMO_MARKER):
        return value

    remainder = value[len(DEMO_MARKER):].strip()
    remainder = remainder.lstrip("|:-").strip()

    # The production demo seeder uses this marker-only service description.
    if not remainder or remainder.lower() == "service":
        return None

    return remainder
