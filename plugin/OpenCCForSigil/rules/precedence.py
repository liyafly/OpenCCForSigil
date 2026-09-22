"""Deterministic rule applicability and precedence."""

from __future__ import annotations

from typing import Iterable

from opencc_backend.configs import base_config as _official_base_config
from .models import Rule


def base_direction(config: str) -> str:
    """Map an optional official Jieba config to its V1 direction."""

    return _official_base_config(config)


def applies_to(
    rule: Rule,
    *,
    config: str,
    profile_id: str | None = None,
    book_fingerprint: str | None = None,
) -> bool:
    if not rule.enabled or rule.type not in {"exact", "protect"}:
        return False
    direction = base_direction(config)
    if rule.direction not in {"*", direction}:
        return False
    if rule.scope == "global":
        return True
    if rule.scope == "profile":
        return bool(profile_id and rule.profile_id == profile_id)
    if rule.scope == "book":
        return bool(book_fingerprint and rule.book_fingerprint == book_fingerprint)
    return False


def type_rank(rule: Rule) -> int:
    return 2 if rule.type == "protect" else 1


def scope_rank(rule: Rule) -> int:
    # The fixed V1 order is protection, book-local, global, profile.
    return {"book": 3, "global": 2, "profile": 1}.get(rule.scope, 0)


def precedence_key(rule: Rule) -> tuple[int, int, int, int, str]:
    """Higher tuple values win, except id is inverted by ``ordered_rules``."""

    return type_rank(rule), scope_rank(rule), int(rule.priority), len(rule.source), rule.id


def ordered_rules(rules: Iterable[Rule]) -> tuple[Rule, ...]:
    """Order rules for a stable match decision.

    At a given source position, precedence is considered before source length;
    this lets an explicit protect rule retain its word while exact terms use
    longest-match among otherwise equal candidates.
    """

    return tuple(
        sorted(
            rules,
            key=lambda rule: (
                -type_rank(rule),
                -scope_rank(rule),
                -len(rule.source),
                -int(rule.priority),
                rule.id,
            ),
        )
    )


__all__ = [
    "applies_to",
    "base_direction",
    "ordered_rules",
    "precedence_key",
    "scope_rank",
    "type_rank",
]
