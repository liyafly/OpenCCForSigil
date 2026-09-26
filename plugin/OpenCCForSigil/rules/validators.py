"""Validation for V1 rule and snapshot data.

Validation errors are intentionally specific enough for a dialog to point to a
row and field.  This module does not silently coerce malformed user data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping
import unicodedata

from .models import (
    Rule,
    RuleSnapshot,
    SUPPORTED_DIRECTIONS,
    SUPPORTED_MATCH_TYPES,
    SUPPORTED_RULE_ACTIONS,
    SUPPORTED_RULE_STAGES,
    SUPPORTED_RULE_TYPES,
    SUPPORTED_SCOPES,
)


class RuleValidationError(ValueError):
    """A user-correctable schema or rule validation failure."""

    def __init__(self, message: str, *, field: str = "", index: int | None = None) -> None:
        self.field = field
        self.index = index
        prefix = f"rule {index}: " if index is not None else ""
        prefix += f"{field}: " if field else ""
        super().__init__(prefix + message)


@dataclass(frozen=True)
class ValidationIssue:
    message: str
    field: str = ""
    index: int | None = None
    blocking: bool = True


def _has_visible_text(value: str) -> bool:
    return any(
        not (character.isspace() or unicodedata.category(character).startswith("P"))
        for character in value
    )


def validate_rule(rule: Rule | Mapping[str, Any], *, index: int | None = None) -> Rule:
    if not isinstance(rule, Rule):
        try:
            rule = Rule.from_dict(rule)
        except (TypeError, ValueError) as exc:
            raise RuleValidationError(str(exc), index=index) from exc
    if not isinstance(rule.id, str) or not rule.id.strip():
        raise RuleValidationError("id must be a non-empty string", field="id", index=index)
    if not isinstance(rule.enabled, bool):
        raise RuleValidationError("enabled must be boolean", field="enabled", index=index)
    if not isinstance(rule.type, str):
        raise RuleValidationError("type must be a string", field="type", index=index)
    if rule.type not in SUPPORTED_RULE_TYPES:
        if rule.type == "regex":
            raise RuleValidationError(
                "regex is a match type, not a legacy rule type (V1.1)",
                field="type", index=index,
            )
        raise RuleValidationError(
            f"must be one of {sorted(SUPPORTED_RULE_TYPES)}", field="type", index=index
        )
    if rule.semantic_version not in {1, 2} or isinstance(rule.semantic_version, bool):
        raise RuleValidationError(
            "semantic_version must be 1 or 2", field="semantic_version", index=index)
    if rule.action not in SUPPORTED_RULE_ACTIONS:
        raise RuleValidationError(
            f"must be one of {sorted(SUPPORTED_RULE_ACTIONS)}", field="action", index=index)
    if rule.match_type not in SUPPORTED_MATCH_TYPES:
        raise RuleValidationError(
            f"must be one of {sorted(SUPPORTED_MATCH_TYPES)}", field="match_type", index=index)
    if rule.stage not in SUPPORTED_RULE_STAGES:
        raise RuleValidationError(
            f"must be one of {sorted(SUPPORTED_RULE_STAGES)}", field="stage", index=index)
    if rule.match_type == "regex":
        raise RuleValidationError(
            "regular expression matching is not available until the guarded engine is bundled",
            field="match_type",
            index=index,
        )
    if rule.action == "replace":
        raise RuleValidationError(
            "staged replacement is not available until source mapping is enabled",
            field="action",
            index=index,
        )
    if rule.semantic_version == 1 and (
        rule.action not in {"protect", "override"}
        or rule.match_type != "literal"
        or rule.stage != "source"
    ):
        raise RuleValidationError(
            "V1 rules must use literal source-stage protect or override behavior",
            field="semantic_version",
            index=index,
        )
    if (rule.action == "protect") != (rule.type == "protect"):
        raise RuleValidationError("type does not agree with action", field="type", index=index)
    if rule.action in {"protect", "override"} and rule.stage != "source":
        raise RuleValidationError(
            "protect and final-writing rules must use the source stage", field="stage", index=index)
    if rule.action == "replace" and rule.stage not in {"pre", "post"}:
        raise RuleValidationError(
            "replace rules must use the pre or post stage", field="stage", index=index)
    if not isinstance(rule.direction, str):
        raise RuleValidationError("direction must be a string", field="direction", index=index)
    if rule.direction not in SUPPORTED_DIRECTIONS:
        raise RuleValidationError(
            "direction is required and must be a supported V1 config or '*'",
            field="direction",
            index=index,
        )
    if not isinstance(rule.scope, str):
        raise RuleValidationError("scope must be a string", field="scope", index=index)
    if rule.scope not in SUPPORTED_SCOPES:
        raise RuleValidationError(
            f"must be one of {sorted(SUPPORTED_SCOPES)}", field="scope", index=index
        )
    if (not isinstance(rule.source, str) or not rule.source
            or (rule.semantic_version == 1 and not _has_visible_text(rule.source))):
        raise RuleValidationError(
            "source must not be empty" if rule.semantic_version >= 2
            else "source must contain visible non-punctuation text",
            field="source", index=index
        )
    if rule.action == "protect" and rule.target not in ("", rule.source):
        raise RuleValidationError("protect target must equal source", field="target", index=index)
    if rule.action != "protect" and not isinstance(rule.target, str):
        raise RuleValidationError("target must be a string", field="target", index=index)
    for field in ("source", "target"):
        value = getattr(rule, field)
        if any(not (char in "\t\n\r" or 0x20 <= ord(char) <= 0xD7FF
                   or 0xE000 <= ord(char) <= 0xFFFD or 0x10000 <= ord(char) <= 0x10FFFF)
               for char in value):
            raise RuleValidationError("text contains an invalid XML character", field=field, index=index)
    if not isinstance(rule.priority, int) or isinstance(rule.priority, bool):
        raise RuleValidationError("priority must be an integer", field="priority", index=index)
    if rule.scope == "profile" and not rule.profile_id:
        raise RuleValidationError(
            "profile scope requires profile_id", field="profile_id", index=index
        )
    if rule.scope == "book" and not rule.book_fingerprint:
        raise RuleValidationError(
            "book scope requires book_fingerprint", field="book_fingerprint", index=index
        )
    for name in ("source_note", "comment", "profile_id", "book_fingerprint"):
        if not isinstance(getattr(rule, name), str):
            raise RuleValidationError("must be a string", field=name, index=index)
    return rule


def validate_rules(rules: Iterable[Rule | Mapping[str, Any]]) -> tuple[Rule, ...]:
    normalized = tuple(validate_rule(item, index=index) for index, item in enumerate(rules))
    by_id = {}
    for rule in normalized:
        if rule.id in by_id and by_id[rule.id] != rule:
            raise RuleValidationError("rule IDs must be unique", field="id")
        by_id[rule.id] = rule
    return normalized


def validate_snapshot(snapshot: RuleSnapshot) -> RuleSnapshot:
    if not isinstance(snapshot, RuleSnapshot):
        raise RuleValidationError("expected RuleSnapshot")
    validate_rules(snapshot.rules)
    return snapshot


__all__ = [
    "RuleValidationError",
    "ValidationIssue",
    "validate_rule",
    "validate_rules",
    "validate_snapshot",
]
