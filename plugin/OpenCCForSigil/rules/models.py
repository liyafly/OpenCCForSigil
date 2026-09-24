"""Immutable models for the user rule overlay.

The rule layer deliberately has no dependency on OpenCC or Sigil.  A rule
snapshot is a value object: callers can safely retain it while a manager edits
its working copy, and the canonical JSON hash makes a plan reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Iterable, Mapping
import uuid


RULE_SCHEMA_VERSION = 1
SUPPORTED_DIRECTIONS = frozenset(
    {
        "s2t",
        "s2tw",
        "s2twp",
        "s2hk",
        "s2hkp",
        "t2s",
        "tw2s",
        "tw2sp",
        "hk2s",
        "hk2sp",
        "t2tw",
        "tw2t",
        "t2hk",
        "hk2t",
        "t2jp",
        "jp2t",
        "*",
    }
)
SUPPORTED_RULE_TYPES = frozenset({"exact", "protect"})
SUPPORTED_SCOPES = frozenset({"global", "profile", "book"})


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_rule_id() -> str:
    return str(uuid.uuid4())


_new_id = new_rule_id


@dataclass(frozen=True)
class Rule:
    """A directional exact or protected overlay rule.

    ``profile_id`` and ``book_fingerprint`` are optional selectors used only
    for their corresponding scopes.  Keeping them on the rule avoids a
    separate mutable registry and means a snapshot is self-contained.
    """

    id: str = field(default_factory=new_rule_id)
    enabled: bool = True
    type: str = "exact"
    direction: str = ""
    source: str = ""
    target: str = ""
    scope: str = "global"
    priority: int = 100
    source_note: str = ""
    comment: str = ""
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    profile_id: str = ""
    book_fingerprint: str = ""

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
        *,
        default_direction: str | None = None,
        default_scope: str = "global",
        profile_id: str = "",
        book_fingerprint: str = "",
    ) -> "Rule":
        values = dict(payload)
        if default_direction and not values.get("direction"):
            values["direction"] = default_direction
        if not values.get("scope"):
            values["scope"] = default_scope
        if profile_id and not values.get("profile_id"):
            values["profile_id"] = profile_id
        if book_fingerprint and not values.get("book_fingerprint"):
            values["book_fingerprint"] = book_fingerprint
        if values.get("type") == "protect" and "target" not in values:
            values["target"] = values.get("source", "")
        allowed = {
            "id",
            "enabled",
            "type",
            "direction",
            "source",
            "target",
            "scope",
            "priority",
            "source_note",
            "comment",
            "created_at",
            "updated_at",
            "profile_id",
            "book_fingerprint",
        }
        unknown = sorted(set(values) - allowed)
        if unknown:
            raise ValueError("unknown rule fields: " + ", ".join(unknown))
        return cls(**{key: value for key, value in values.items() if key in allowed})

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "enabled": self.enabled,
            "type": self.type,
            "direction": self.direction,
            "source": self.source,
            "target": self.source if self.type == "protect" else self.target,
            "scope": self.scope,
            "priority": self.priority,
            "source_note": self.source_note,
            "comment": self.comment,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "profile_id": self.profile_id,
            "book_fingerprint": self.book_fingerprint,
        }

    @property
    def is_protect(self) -> bool:
        return self.type == "protect"


def canonical_rule_dict(rule: Rule) -> dict[str, Any]:
    """Return deterministic semantic data used for snapshot identity.

    Timestamps document editing history but do not alter conversion semantics;
    excluding them keeps two equivalent in-memory rules hash-identical.
    """

    value = rule.to_dict()
    value.pop("created_at", None)
    value.pop("updated_at", None)
    return value


def canonical_rules_json(rules: Iterable[Rule]) -> bytes:
    payload = [canonical_rule_dict(rule) for rule in sorted(rules, key=lambda item: item.id)]
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


@dataclass(frozen=True)
class RuleSnapshot:
    """Frozen rules plus a content hash captured at plan time."""

    schema_version: int = RULE_SCHEMA_VERSION
    rules: tuple[Rule, ...] = ()
    sha256: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "rules", tuple(self.rules))
        expected = hashlib.sha256(canonical_rules_json(self.rules)).hexdigest()
        if self.sha256 and self.sha256 != expected:
            raise ValueError("rules snapshot sha256 does not match its rules")
        if not self.sha256:
            object.__setattr__(self, "sha256", expected)
        if self.schema_version != RULE_SCHEMA_VERSION:
            raise ValueError(f"unsupported rule snapshot schema_version: {self.schema_version}")

    @classmethod
    def freeze(
        cls, rules: Iterable[Rule | Mapping[str, Any]], *, schema_version: int = 1
    ) -> "RuleSnapshot":
        normalized = tuple(
            item if isinstance(item, Rule) else Rule.from_dict(item) for item in rules
        )
        return cls(schema_version=schema_version, rules=normalized)

    build = freeze
    from_rules = freeze

    @property
    def rules_hash(self) -> str:
        """Compatibility alias for the core's existing RuleSnapshot field."""

        return self.sha256

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sha256": self.sha256,
            "rules": [rule.to_dict() for rule in self.rules],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuleSnapshot":
        if not isinstance(payload, Mapping) or not isinstance(payload.get("rules"), list):
            raise ValueError("rule snapshot must contain a rules array")
        rules = tuple(Rule.from_dict(item) for item in payload["rules"])
        # Validate here rather than waiting for conversion so persisted/imported
        # snapshots fail at their boundary with a field-specific error.
        from .validators import validate_rules

        validate_rules(rules)
        expected = payload.get("sha256", "")
        if not isinstance(expected, str):
            raise ValueError("rule snapshot sha256 must be a string")
        version = payload.get("schema_version", 1)
        if not isinstance(version, int) or isinstance(version, bool):
            raise ValueError("rule snapshot schema_version must be an integer")
        return cls(
            schema_version=version,
            rules=rules,
            sha256=expected,
        )


__all__ = [
    "RULE_SCHEMA_VERSION",
    "SUPPORTED_DIRECTIONS",
    "SUPPORTED_RULE_TYPES",
    "SUPPORTED_SCOPES",
    "Rule",
    "RuleSnapshot",
    "new_rule_id",
    "canonical_rule_dict",
    "canonical_rules_json",
]
