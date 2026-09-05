"""Log retention boundary.

Retention is intentionally not invoked by the Phase 0 no-op path. The
deletion policy will be implemented together with user-configurable history
retention and explicit cleanup UI.
"""


def retention_policy() -> dict:
    """Describe the specification default without deleting anything."""

    return {"max_sessions": 50, "max_age_days": 30}
