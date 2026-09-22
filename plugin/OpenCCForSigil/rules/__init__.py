"""Directional user-rule overlay layer."""

from .engine import OverlayResult, convert_with_overlay, lock_spans
from .models import Rule, RuleSnapshot
from .validators import RuleValidationError, validate_rule, validate_rules

__all__ = [
    "OverlayResult",
    "Rule",
    "RuleSnapshot",
    "RuleValidationError",
    "convert_with_overlay",
    "lock_spans",
    "validate_rule",
    "validate_rules",
]
