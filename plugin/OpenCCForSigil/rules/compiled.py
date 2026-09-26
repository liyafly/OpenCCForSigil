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
        candidates = ordered_rules(
            rule for rule in rules
            if applies_to(rule, config=config, profile_id=profile_id,
                          book_fingerprint=book_fingerprint)
        )
        # Conflict scope is the rules that can participate in this run. A
        # different direction, profile, or book must not prevent an unrelated
        # conversion from starting.
        validate_no_blocking_conflicts(candidates)
        buckets: dict[str, list[Rule]] = {}
        for rule in candidates:
            buckets.setdefault(rule.source[0], []).append(rule)
        index = MappingProxyType({key: tuple(values) for key, values in buckets.items()})
        return cls(actual_hash, config, profile_id, book_fingerprint, candidates, index)


def lock_spans_compiled(text: str, overlay: CompiledOverlay):
    """Return deterministic matches after reserving all protected ranges."""

    from .engine import LockedSpan

    protected = []
    cursor = 0
    while cursor < len(text):
        match = next(
            (
                rule for rule in overlay.index.get(text[cursor], ())
                if rule.type == "protect" and text.startswith(rule.source, cursor)
            ),
            None,
        )
        if match is None:
            cursor += 1
            continue
        end = cursor + len(match.source)
        protected.append(LockedSpan(cursor, end, match.source, match.source, match))
        cursor = end

    spans = []
    protected_index = 0
    cursor = 0
    while cursor < len(text):
        while protected_index < len(protected) and protected[protected_index].end <= cursor:
            protected_index += 1
        if (protected_index < len(protected)
                and protected[protected_index].start == cursor):
            span = protected[protected_index]
            spans.append(span)
            cursor = span.end
            protected_index += 1
            continue

        match = None
        for rule in overlay.index.get(text[cursor], ()):
            if not text.startswith(rule.source, cursor):
                continue
            end = cursor + len(rule.source)
            if (rule.type != "protect" and protected_index < len(protected)
                    and protected[protected_index].start < end):
                continue
            match = rule
            break
        if match is None:
            cursor += 1
            continue
        end = cursor + len(match.source)
        spans.append(LockedSpan(cursor, end, match.source, match.target, match))
        cursor = end
    return tuple(spans)


__all__ = ["CompiledOverlay", "lock_spans_compiled"]
