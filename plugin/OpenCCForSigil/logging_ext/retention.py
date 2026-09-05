"""Log retention boundary.

Retention remains a separate policy service; conversion does not delete old
history as a side effect of a session.
"""


def retention_policy() -> dict:
    """Describe the specification default without deleting anything."""

    return {"max_sessions": 50, "max_age_days": 30}
