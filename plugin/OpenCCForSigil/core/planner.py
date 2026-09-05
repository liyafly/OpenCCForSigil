"""Immutable ConversionPlan construction boundary."""

from core.models import ConversionPlan


def plan_not_implemented() -> None:
    """Keep the Phase 0 boundary explicit until document targets exist."""

    raise NotImplementedError("ConversionPlan construction starts in Phase 1/2")


__all__ = ["ConversionPlan", "plan_not_implemented"]
