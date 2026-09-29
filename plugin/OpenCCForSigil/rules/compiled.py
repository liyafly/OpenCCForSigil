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
    LiteralPrefixIndex,
    RegexBudget,
    RuleExecutionError,
    SkippedRuleMatch,
    _indexed_stage_candidates,
    source_matches,
)


@dataclass(frozen=True)
class LockedSpan:
    start: int
    end: int
    source: str
    target: str
    rule: Rule

    @property
    def rule_id(self) -> str:
        return self.rule.id


@dataclass(frozen=True)
class CompiledOverlay:
    """Validated rules, ordered once and indexed by their first source character."""

    rules_hash: str
    config: str
    profile_id: str | None
    book_fingerprint: str | None
    rules: tuple[Rule, ...]
    regex_patterns: Mapping[str, object]
    source_rules: tuple[Rule, ...]
    pre_rules: tuple[Rule, ...]
    post_rules: tuple[Rule, ...]
    source_rule_order: Mapping[str, int]
    pre_rule_order: Mapping[str, int]
    post_rule_order: Mapping[str, int]
    source_literal_index: Mapping[str, tuple[Rule, ...]]
    pre_literal_index: Mapping[str, tuple[Rule, ...]]
    post_literal_index: Mapping[str, tuple[Rule, ...]]

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
        source_rules = tuple(rule for rule in candidates if rule.stage == "source")
        pre_rules = tuple(
            rule for rule in candidates if rule.action == "replace" and rule.stage == "pre")
        post_rules = tuple(
            rule for rule in candidates if rule.action == "replace" and rule.stage == "post")

        def stage_indexes(stage_rules):
            rule_order = MappingProxyType({
                rule.id: position for position, rule in enumerate(stage_rules)
            })
            literal_buckets: dict[str, list[Rule]] = {}
            for rule in stage_rules:
                if rule.match_type == "literal" and rule.source:
                    prefix = rule.source[:2]
                    literal_buckets.setdefault(prefix, []).append(rule)
            literal_buckets = MappingProxyType({
                key: tuple(values) for key, values in literal_buckets.items()
            })
            single_char_buckets = MappingProxyType({
                key: values for key, values in literal_buckets.items() if len(key) == 1
            })
            return rule_order, LiteralPrefixIndex(literal_buckets, single_char_buckets)

        source_rule_order, source_literal_index = stage_indexes(source_rules)
        pre_rule_order, pre_literal_index = stage_indexes(pre_rules)
        post_rule_order, post_literal_index = stage_indexes(post_rules)
        return cls(
            rules_hash=actual_hash,
            config=config,
            profile_id=profile_id,
            book_fingerprint=book_fingerprint,
            rules=candidates,
            regex_patterns=MappingProxyType(patterns),
            source_rules=source_rules,
            pre_rules=pre_rules,
            post_rules=post_rules,
            source_rule_order=source_rule_order,
            pre_rule_order=pre_rule_order,
            post_rule_order=post_rule_order,
            source_literal_index=source_literal_index,
            pre_literal_index=pre_literal_index,
            post_literal_index=post_literal_index,
        )


def lock_spans_compiled(
    text: str,
    overlay: CompiledOverlay,
    budget: RegexBudget | None = None,
    *,
    skipped: list[SkippedRuleMatch] | None = None,
):
    """Return deterministic matches after reserving all protected ranges."""

    budget = budget or RegexBudget()
    regex_rules = (
        tuple(rule for rule in overlay.source_rules if rule.match_type == "regex")
        if overlay.regex_patterns else ()
    )
    source_rules = _indexed_stage_candidates(
        text, regex_rules, overlay.source_literal_index, overlay.source_rule_order)
    return tuple(
        LockedSpan(
            match.start,
            match.end,
            match.rule.source if match.rule.match_type == "literal"
            else text[match.start:match.end],
            match.target,
            match.rule,
        )
        for match in source_matches(
            text, source_rules, overlay.regex_patterns, budget, skipped=skipped)
    )


__all__ = ["CompiledOverlay", "LockedSpan", "lock_spans_compiled"]
