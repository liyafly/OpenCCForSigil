"""Conflict detection for imported and active rule sets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import Rule
from .validators import validate_rules


@dataclass(frozen=True)
class RuleConflict:
    kind: str
    source: str
    rules: tuple[Rule, ...]
    blocking: bool = True

    @property
    def message(self) -> str:
        targets = ", ".join(
            f"{rule.scope}/{rule.direction} → {rule.target or rule.source} [{rule.id}]"
            for rule in self.rules
        )
        prefix = "BLOCKING CONFLICT: " if self.blocking else ""
        return f"{prefix}{self.kind}: {self.source!r} ({targets})"


class BlockingRuleConflict(ValueError):
    """Raised before overlay matching when a blocking conflict is present."""

    def __init__(self, conflicts: Iterable[RuleConflict]):
        self.conflicts = tuple(conflicts)
        super().__init__(
            "blocking rule conflicts: " + "; ".join(item.message for item in self.conflicts)
        )


def find_conflicts(rules: Iterable[Rule]) -> tuple[RuleConflict, ...]:
    checked = validate_rules(rules)
    conflicts: list[RuleConflict] = []
    by_key: dict[tuple[str, str, str, str, int, str, str], list[Rule]] = {}
    for rule in checked:
        if not rule.enabled:
            continue
        key = (
            rule.scope,
            rule.direction,
            rule.source,
            rule.type,
            rule.priority,
            rule.profile_id if rule.scope == "profile" else "",
            rule.book_fingerprint if rule.scope == "book" else "",
        )
        by_key.setdefault(key, []).append(rule)
    for (
        _scope,
        _direction,
        source,
        kind,
        _priority,
        _profile_id,
        _book_fingerprint,
    ), group in by_key.items():
        if len(group) < 2:
            continue
        targets = {rule.source if rule.type == "protect" else rule.target for rule in group}
        if len(targets) == 1:
            conflicts.append(
                RuleConflict("DUPLICATE", source, tuple(sorted(group, key=lambda r: r.id)), False)
            )
            continue
        category = "PROTECTED_CONFLICT" if kind == "protect" else "SAME_SOURCE_DIFFERENT_TARGET"
        conflicts.append(
            RuleConflict(category, source, tuple(sorted(group, key=lambda r: r.id)), True)
        )

    # A wildcard and a concrete direction with the same scope/source may both
    # apply.  Different targets are a blocking overlap because no deterministic
    # direction choice could satisfy both declarations.
    by_overlap: dict[tuple[str, str, str, int, str, str], list[Rule]] = {}
    for rule in checked:
        if not rule.enabled:
            continue
        if rule.direction == "*":
            by_overlap.setdefault(
                (
                    rule.scope,
                    rule.source,
                    rule.type,
                    rule.priority,
                    rule.profile_id if rule.scope == "profile" else "",
                    rule.book_fingerprint if rule.scope == "book" else "",
                ),
                [],
            ).append(rule)
    for rule in checked:
        if not rule.enabled or rule.direction == "*":
            continue
        group = by_overlap.get(
            (
                rule.scope,
                rule.source,
                rule.type,
                rule.priority,
                rule.profile_id if rule.scope == "profile" else "",
                rule.book_fingerprint if rule.scope == "book" else "",
            ),
            [],
        )
        for wildcard in group:
            if (wildcard.target or wildcard.source) != (rule.target or rule.source):
                conflicts.append(
                    RuleConflict("DIRECTION_OVERLAP", rule.source, (wildcard, rule), True)
                )
    return _unique_conflicts(conflicts)


def blocking_conflicts(rules: Iterable[Rule]) -> tuple[RuleConflict, ...]:
    return tuple(item for item in find_conflicts(rules) if item.blocking)


detect_conflicts = find_conflicts


def validate_no_blocking_conflicts(rules: Iterable[Rule]) -> tuple[RuleConflict, ...]:
    conflicts = blocking_conflicts(rules)
    if conflicts:
        raise BlockingRuleConflict(conflicts)
    return find_conflicts(rules)


def _unique_conflicts(conflicts: Iterable[RuleConflict]) -> tuple[RuleConflict, ...]:
    result: list[RuleConflict] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    for conflict in conflicts:
        key = (conflict.kind, conflict.source, tuple(rule.id for rule in conflict.rules))
        if key not in seen:
            seen.add(key)
            result.append(conflict)
    return tuple(result)


__all__ = [
    "BlockingRuleConflict",
    "RuleConflict",
    "blocking_conflicts",
    "detect_conflicts",
    "find_conflicts",
    "validate_no_blocking_conflicts",
]
