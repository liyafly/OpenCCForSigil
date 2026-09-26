"""Plan-scoped, indexed rule overlays for repeated text conversion."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType
from typing import Mapping

from .conflicts import validate_no_blocking_conflicts
from .models import RULE_SCHEMA_VERSION, Rule, canonical_rules_json
from .precedence import applies_to, ordered_rules
from .validators import validate_rule, validate_rules
from .matching import (
    REGEX_MAX_PATTERN_CHARS,
    REGEX_MAX_RULES,
    RegexBudget,
    RuleExecutionError,
    source_matches,
)


@dataclass(frozen=True)
class CompiledOverlay:
    """Validated rules, ordered once and indexed by their first source character."""

    rules_hash: str
    config: str
    profile_id: str | None
    book_fingerprint: str | None
    rules: tuple[Rule, ...]
    index: Mapping[str, tuple[Rule, ...]]
    regex_patterns: Mapping[str, object]

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
        regex_rules = tuple(rule for rule in candidates if rule.match_type == "regex")
        if len(regex_rules) > REGEX_MAX_RULES:
            raise ValueError(f"at most {REGEX_MAX_RULES} active regular-expression rules are allowed")
        patterns = {}
        if regex_rules:
            from .regex_runtime import RegexRuntimeError, load_regex_module

            try:
                regex_module = load_regex_module()
            except RegexRuntimeError as exc:
                raise RuleExecutionError(str(exc)) from exc
            for rule in regex_rules:
                validate_rule(rule)
                if len(rule.source) > REGEX_MAX_PATTERN_CHARS:
                    raise ValueError(
                        f"rule {rule.id}: regular-expression pattern exceeds "
                        f"{REGEX_MAX_PATTERN_CHARS} characters")
                try:
                    patterns[rule.id] = regex_module.compile(rule.source, regex_module.VERSION1)
                except Exception as exc:
                    raise ValueError(f"rule {rule.id}: invalid regular expression: {exc}") from exc
        for rule in candidates:
            if rule.match_type == "regex":
                continue
            buckets.setdefault(rule.source[0], []).append(rule)
        index = MappingProxyType({key: tuple(values) for key, values in buckets.items()})
        return cls(actual_hash, config, profile_id, book_fingerprint, candidates, index,
                   MappingProxyType(patterns))


def lock_spans_compiled(text: str, overlay: CompiledOverlay, budget: RegexBudget | None = None):
    """Return deterministic matches after reserving all protected ranges."""

    from .engine import LockedSpan
    budget = budget or RegexBudget()
    source_rules = tuple(rule for rule in overlay.rules if rule.stage == "source")
    return tuple(
        LockedSpan(match.start, match.end, text[match.start:match.end], match.target, match.rule)
        for match in source_matches(text, source_rules, dict(overlay.regex_patterns), budget)
    )


__all__ = ["CompiledOverlay", "lock_spans_compiled"]
