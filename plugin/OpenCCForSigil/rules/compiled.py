"""Plan-scoped, indexed rule overlays for repeated text conversion."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType
from typing import Mapping

from .conflicts import validate_no_blocking_conflicts
from .models import RULE_SCHEMA_VERSION, Rule, canonical_rules_json
from .precedence import applies_to, ordered_rules
from .validators import validate_rules


@dataclass(frozen=True)
class CompiledOverlay:
    """Validated rules, ordered once and indexed by their first source character."""

    rules_hash: str
    config: str
    profile_id: str | None
    book_fingerprint: str | None
    rules: tuple[Rule, ...]
    index: Mapping[str, tuple[Rule, ...]]

    @classmethod
    def build(
        cls,
        snapshot,
        *,
        expected_hash: str | None = None,
        config: str,
        profile_id: str | None = None,
        book_fingerprint: str | None = None,
    ) -> "CompiledOverlay":
        """Validate a frozen snapshot once and prepare its applicable rules."""

        version = getattr(snapshot, "schema_version", RULE_SCHEMA_VERSION)
        if version != RULE_SCHEMA_VERSION:
            raise ValueError(f"unsupported rule snapshot schema_version: {version}")
        rules = validate_rules(snapshot.rules)
        actual_hash = sha256(canonical_rules_json(rules)).hexdigest()
        requested_hash = expected_hash or getattr(
            snapshot, "rules_hash", getattr(snapshot, "sha256", ""))
        if actual_hash != requested_hash:
            raise ValueError("rule snapshot hash mismatch")
        validate_no_blocking_conflicts(rules)

        candidates = ordered_rules(
            rule for rule in rules
            if applies_to(rule, config=config, profile_id=profile_id,
                          book_fingerprint=book_fingerprint)
        )
        buckets: dict[str, list[Rule]] = {}
        for rule in candidates:
            buckets.setdefault(rule.source[0], []).append(rule)
        index = MappingProxyType({key: tuple(values) for key, values in buckets.items()})
        return cls(actual_hash, config, profile_id, book_fingerprint, candidates, index)


def lock_spans_compiled(text: str, overlay: CompiledOverlay):
    """Return the same deterministic matches as ``lock_spans`` using one bucket."""

    from .engine import LockedSpan

    spans = []
    cursor = 0
    while cursor < len(text):
        match = next((rule for rule in overlay.index.get(text[cursor], ())
                      if text.startswith(rule.source, cursor)), None)
        if match is None:
            cursor += 1
            continue
        end = cursor + len(match.source)
        target = match.source if match.type == "protect" else match.target
        spans.append(LockedSpan(cursor, end, match.source, target, match))
        cursor = end
    return tuple(spans)


__all__ = ["CompiledOverlay", "lock_spans_compiled"]
