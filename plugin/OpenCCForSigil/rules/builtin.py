"""Narrow built-in protections for known context-sensitive conversion cases."""

from __future__ import annotations

from typing import Iterable

from opencc_backend.configs import base_config
from .models import Rule


AUTHOR_CREDIT_PROTECTION = Rule(
    id="builtin-author-credit-tw2sp",
    type="protect",
    direction="tw2sp",
    source="◎【著】",
    target="◎【著】",
    scope="global",
    source_note="OpenCCForSigil built-in context protection",
    comment="Keep this Taiwan-to-Simplified author-credit marker unchanged.",
)

BUILTIN_RULES = (AUTHOR_CREDIT_PROTECTION,)


def with_builtin_rules(rules: Iterable[Rule], *, config: str) -> tuple[Rule, ...]:
    """Return user rules together with the current, non-overridable defaults."""

    user_rules = tuple(rules)
    if base_config(config) != AUTHOR_CREDIT_PROTECTION.direction:
        return user_rules
    builtin_ids = {rule.id for rule in BUILTIN_RULES}
    cleaned_rules = tuple(rule for rule in user_rules if rule.id not in builtin_ids)
    return (*cleaned_rules, *BUILTIN_RULES)


__all__ = ["AUTHOR_CREDIT_PROTECTION", "BUILTIN_RULES", "with_builtin_rules"]
