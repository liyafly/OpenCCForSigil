"""Plan-scoped, indexed rule overlays for repeated text conversion."""

from __future__ import annotations

from collections import OrderedDict
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
    _indexed_stage_candidates,
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
    source_rules: tuple[Rule, ...]
    pre_rules: tuple[Rule, ...]
    post_rules: tuple[Rule, ...]
    source_regex_rules: tuple[Rule, ...]
    pre_regex_rules: tuple[Rule, ...]
    post_regex_rules: tuple[Rule, ...]
    guarded: bool
    source_rule_order: Mapping[str, int]
    pre_rule_order: Mapping[str, int]
    post_rule_order: Mapping[str, int]
    source_literal_index: Mapping[str, tuple[Rule, ...]]
    pre_literal_index: Mapping[str, tuple[Rule, ...]]
    post_literal_index: Mapping[str, tuple[Rule, ...]]
    source_has_single_char_literals: bool
    pre_has_single_char_literals: bool
    post_has_single_char_literals: bool

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

        source_rules = tuple(rule for rule in candidates if rule.stage == "source")
        pre_rules = tuple(
            rule for rule in candidates if rule.action == "replace" and rule.stage == "pre")
        post_rules = tuple(
            rule for rule in candidates if rule.action == "replace" and rule.stage == "post")

        def stage_indexes(stage_rules):
            rule_order = MappingProxyType({
                rule.id: position for position, rule in enumerate(stage_rules)
            })
            regex_rules = tuple(rule for rule in stage_rules if rule.match_type == "regex")
            literal_buckets: dict[str, list[Rule]] = {}
            has_single_char_literals = False
            for rule in stage_rules:
                if rule.match_type == "literal" and rule.source:
                    prefix = rule.source[:2]
                    if len(prefix) == 1:
                        has_single_char_literals = True
                    literal_buckets.setdefault(prefix, []).append(rule)
            literal_index = MappingProxyType({
                key: tuple(values) for key, values in literal_buckets.items()
            })
            return regex_rules, rule_order, literal_index, has_single_char_literals

        (source_regex_rules, source_rule_order, source_literal_index,
         source_has_single_char_literals) = stage_indexes(source_rules)
        pre_regex_rules, pre_rule_order, pre_literal_index, pre_has_single_char_literals = (
            stage_indexes(pre_rules))
        post_regex_rules, post_rule_order, post_literal_index, post_has_single_char_literals = (
            stage_indexes(post_rules))
        return cls(
            rules_hash=actual_hash,
            config=config,
            profile_id=profile_id,
            book_fingerprint=book_fingerprint,
            rules=candidates,
            index=index,
            regex_patterns=MappingProxyType(patterns),
            source_rules=source_rules,
            pre_rules=pre_rules,
            post_rules=post_rules,
            source_regex_rules=source_regex_rules,
            pre_regex_rules=pre_regex_rules,
            post_regex_rules=post_regex_rules,
            guarded=any(
                rule.match_type == "regex" or rule.action == "replace"
                for rule in candidates
            ),
            source_rule_order=source_rule_order,
            pre_rule_order=pre_rule_order,
            post_rule_order=post_rule_order,
            source_literal_index=source_literal_index,
            pre_literal_index=pre_literal_index,
            post_literal_index=post_literal_index,
            source_has_single_char_literals=source_has_single_char_literals,
            pre_has_single_char_literals=pre_has_single_char_literals,
            post_has_single_char_literals=post_has_single_char_literals,
        )


def lock_spans_compiled(
    text: str,
    overlay: CompiledOverlay,
    budget: RegexBudget | None = None,
    *,
    candidate_cache: OrderedDict[str, tuple[Rule, ...]] | None = None,
):
    """Return deterministic matches after reserving all protected ranges."""

    from .engine import LockedSpan
    budget = budget or RegexBudget()
    source_rules = candidate_cache.get(text) if candidate_cache is not None and len(text) <= 512 else None
    if source_rules is None:
        source_rules = _indexed_stage_candidates(
            text,
            overlay.source_regex_rules,
            overlay.source_literal_index,
            overlay.source_rule_order,
            include_single_char_rules=overlay.source_has_single_char_literals,
        )
        if candidate_cache is not None and len(text) <= 512:
            candidate_cache[text] = source_rules
            candidate_cache.move_to_end(text)
            if len(candidate_cache) > 256:
                candidate_cache.popitem(last=False)
    elif candidate_cache is not None:
        candidate_cache.move_to_end(text)
    return tuple(
        LockedSpan(
            match.start,
            match.end,
            match.rule.source if match.rule.match_type == "literal"
            else text[match.start:match.end],
            match.target,
            match.rule,
        )
        for match in source_matches(text, source_rules, overlay.regex_patterns, budget)
    )


__all__ = ["CompiledOverlay", "lock_spans_compiled"]
