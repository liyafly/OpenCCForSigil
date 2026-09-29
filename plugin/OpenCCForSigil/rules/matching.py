"""Bounded literal and regular-expression rule matching."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

from .models import Rule
from .precedence import scope_rank, type_rank


REGEX_MATCH_TIMEOUT_SECONDS = 0.05
REGEX_MAX_RULES = 128
REGEX_MAX_PATTERN_CHARS = 512
REGEX_MAX_HITS_PER_RULE = 512
REGEX_MAX_CANDIDATES_PER_FRAGMENT = 20_000
REGEX_MAX_CANDIDATE_OUTPUT_CHARS_PER_FRAGMENT = 2_000_000


class RuleExecutionError(RuntimeError):
    """A rule could not be applied within the guarded matching limits."""


@dataclass(frozen=True)
class RuleMatch:
    rule: Rule
    start: int
    end: int
    target: str


@dataclass(frozen=True)
class StageHit:
    rule: Rule
    start: int
    end: int
    source: str
    target: str


@dataclass(frozen=True)
class SkippedRuleMatch:
    rule_id: str
    winner_id: str
    start: int
    end: int


@dataclass(frozen=True)
class LiteralPrefixIndex(Mapping[str, tuple[Rule, ...]]):
    """Immutable literal-prefix buckets, with one-character buckets indexed separately."""

    buckets: Mapping[str, tuple[Rule, ...]]
    single_char_buckets: Mapping[str, tuple[Rule, ...]]

    def __getitem__(self, key: str) -> tuple[Rule, ...]:
        return self.buckets[key]

    def __iter__(self):
        return iter(self.buckets)

    def __len__(self) -> int:
        return len(self.buckets)


class RegexBudget:
    """Collect per-fragment diagnostics for regex matches."""

    def __init__(self) -> None:
        self.zero_width_skips: dict[str, int] = {}

    def timeout_for(self, _rule: Rule, _position: int) -> float:
        return REGEX_MATCH_TIMEOUT_SECONDS

    def note_regex_hit(
        self, rule: Rule, position: int, fragment_hits: dict[str, int]
    ) -> None:
        count = fragment_hits.get(rule.id, 0) + 1
        fragment_hits[rule.id] = count
        if count > REGEX_MAX_HITS_PER_RULE:
            raise RuleExecutionError(
                f"rule {rule.id}: regular expression exceeded {REGEX_MAX_HITS_PER_RULE} "
                f"hits near offset {position}")


def _resolve_same_start(candidates: list[RuleMatch]) -> RuleMatch:
    legacy = all(candidate.rule.semantic_version <= 1 for candidate in candidates)

    def rank(candidate: RuleMatch) -> tuple[int, int, int, int]:
        rule = candidate.rule
        return (
            type_rank(rule), scope_rank(rule, legacy=legacy),
            candidate.end - candidate.start, int(rule.priority),
        )

    best_rank = max(rank(candidate) for candidate in candidates)
    best = [candidate for candidate in candidates if rank(candidate) == best_rank]
    targets = {candidate.target for candidate in best}
    if len(targets) > 1:
        ids = ", ".join(sorted(candidate.rule.id for candidate in best))
        raise RuleExecutionError(
            f"rules {ids} have the same precedence and different outputs at "
            f"offset {best[0].start}")
    return min(best, key=lambda candidate: candidate.rule.id)


def literal_candidates(
    text: str,
    index: Mapping[str, tuple[Rule, ...]],
    order: Mapping[str, int],
) -> tuple[Rule, ...]:
    """Return indexed literal rules whose one/two-character prefix occurs."""

    keys = {text[position:position + 2] for position in range(len(text) - 1)}
    if isinstance(index, LiteralPrefixIndex):
        buckets = index.buckets
        found = [rule for key in keys for rule in buckets.get(key, ())]
        if index.single_char_buckets:
            single_buckets = index.single_char_buckets
            found.extend(
                rule for key in set(text) for rule in single_buckets.get(key, ()))
    else:
        keys.update(text)
        found = [rule for key in keys for rule in index.get(key, ())]
    found.sort(key=lambda rule: order[rule.id])
    return tuple(found)


def _indexed_stage_candidates(
    text: str,
    regex_rules: tuple[Rule, ...],
    literal_index: Mapping[str, tuple[Rule, ...]],
    order: Mapping[str, int],
) -> tuple[Rule, ...]:
    literals = literal_candidates(text, literal_index, order)
    if not literals:
        return regex_rules
    if not regex_rules:
        return literals
    candidates = [*literals, *regex_rules]
    candidates.sort(key=lambda rule: order[rule.id])
    return tuple(candidates)


def collect_matches(
    text: str,
    rules: tuple[Rule, ...],
    regex_patterns: Mapping[str, object],
    budget: RegexBudget,
) -> tuple[RuleMatch, ...]:
    """Collect candidates from one immutable stage input; matches may overlap."""

    matches: list[RuleMatch] = []
    candidate_output_chars = 0
    for rule in rules:
        if rule.match_type == "literal":
            source = rule.source
            source_length = len(source)
            final_start = len(text) - source_length
            cursor = 0
            while source and cursor <= final_start:
                start = text.find(source, cursor)
                if start < 0:
                    break
                end = start + source_length
                target = text[start:end] if rule.action == "protect" else rule.target
                matches.append(RuleMatch(rule, start, end, target))
                cursor = start + 1
            continue

        pattern = regex_patterns.get(rule.id)
        if pattern is None:
            raise RuleExecutionError(f"rule {rule.id}: compiled regular expression is missing")
        cursor = 0
        candidates = 0
        while cursor <= len(text):
            timeout = budget.timeout_for(rule, cursor)
            try:
                found = pattern.search(text, cursor, timeout=timeout)
            except TimeoutError as exc:
                raise RuleExecutionError(
                    f"rule {rule.id}: regular-expression matching timed out near "
                    f"offset {cursor}") from exc
            except Exception as exc:
                raise RuleExecutionError(
                    f"rule {rule.id}: regular-expression matching failed near "
                    f"offset {cursor}: {exc}") from exc
            if found is None:
                break
            if found.start() == found.end():
                budget.zero_width_skips[rule.id] = (
                    budget.zero_width_skips.get(rule.id, 0) + 1)
                cursor = found.start() + 1
                continue
            candidates += 1
            if candidates > REGEX_MAX_CANDIDATES_PER_FRAGMENT:
                raise RuleExecutionError(
                    f"rule {rule.id}: regular expression produced more than "
                    f"{REGEX_MAX_CANDIDATES_PER_FRAGMENT} candidates near offset "
                    f"{found.start()}")
            matched_text = text[found.start():found.end()]
            if rule.action == "protect":
                target = matched_text
            else:
                references = len(re.findall(r"\\(?:[1-9]|g<[^>]+>)", rule.target))
                upper_bound = len(rule.target) + len(matched_text) * references
                if candidate_output_chars + upper_bound > REGEX_MAX_CANDIDATE_OUTPUT_CHARS_PER_FRAGMENT:
                    raise RuleExecutionError(
                        f"rule {rule.id}: replacement candidate exceeds "
                        f"{REGEX_MAX_CANDIDATE_OUTPUT_CHARS_PER_FRAGMENT} characters "
                        f"near offset {found.start()}")
                try:
                    target = found.expand(rule.target)
                except (IndexError, KeyError, ValueError) as exc:
                    raise RuleExecutionError(
                        f"rule {rule.id}: invalid replacement template at "
                        f"offset {found.start()}: {exc}") from exc
                candidate_output_chars += len(target)
                if candidate_output_chars > REGEX_MAX_CANDIDATE_OUTPUT_CHARS_PER_FRAGMENT:
                    raise RuleExecutionError(
                        f"rule {rule.id}: replacement candidate memory exceeded "
                        f"{REGEX_MAX_CANDIDATE_OUTPUT_CHARS_PER_FRAGMENT} characters "
                        f"near offset {found.start()}")
            matches.append(RuleMatch(rule, found.start(), found.end(), target))
            # Advancing one code point preserves candidates that overlap this hit.
            cursor = found.start() + 1
    return tuple(matches)


def _note_skipped(
    skipped: list[SkippedRuleMatch] | None,
    candidate: RuleMatch | list[RuleMatch],
    winner: RuleMatch | None,
) -> None:
    if skipped is None or winner is None:
        return
    candidates = candidate if isinstance(candidate, list) else [candidate]
    skipped.extend(SkippedRuleMatch(
        item.rule.id, winner.rule.id, item.start, item.end) for item in candidates)


def source_matches(
    text: str,
    rules: tuple[Rule, ...],
    regex_patterns: Mapping[str, object],
    budget: RegexBudget,
    *,
    skipped: list[SkippedRuleMatch] | None = None,
) -> tuple[RuleMatch, ...]:
    """Reserve protections first, then choose final-wording matches."""

    candidates = collect_matches(text, rules, regex_patterns, budget)
    fragment_hits: dict[str, int] = {}
    protected_candidates: dict[int, RuleMatch | list[RuleMatch]] = {}
    override_candidates: dict[int, RuleMatch | list[RuleMatch]] = {}
    for candidate in candidates:
        bucket = protected_candidates if candidate.rule.action == "protect" else override_candidates
        previous = bucket.get(candidate.start)
        if previous is None:
            bucket[candidate.start] = candidate
        elif isinstance(previous, list):
            previous.append(candidate)
        else:
            bucket[candidate.start] = [previous, candidate]

    protected = []
    cursor = 0
    protected_winner: RuleMatch | None = None
    for start in sorted(protected_candidates):
        if start < cursor:
            _note_skipped(skipped, protected_candidates[start], protected_winner)
            continue
        same_start = protected_candidates[start]
        chosen = _resolve_same_start(same_start) if isinstance(same_start, list) else same_start
        if chosen.rule.match_type == "regex":
            budget.note_regex_hit(chosen.rule, chosen.start, fragment_hits)
        protected.append(chosen)
        cursor = chosen.end
        protected_winner = chosen

    spans = []
    cursor = 0
    cursor_winner = None
    protected_index = 0
    for start in sorted(override_candidates):
        while protected_index < len(protected) and protected[protected_index].end <= start:
            spans.append(protected[protected_index])
            protected_index += 1
        if start < cursor:
            _note_skipped(skipped, override_candidates[start], cursor_winner)
            continue
        same_start = override_candidates[start]
        blocker = (protected[protected_index]
                   if protected_index < len(protected) else None)
        if isinstance(same_start, list):
            allowed = (same_start if blocker is None else
                       [candidate for candidate in same_start
                        if candidate.end <= blocker.start])
            if blocker is not None:
                _note_skipped(
                    skipped,
                    [candidate for candidate in same_start
                     if candidate.end > blocker.start],
                    blocker,
                )
            if not allowed:
                continue
            chosen = _resolve_same_start(allowed) if len(allowed) > 1 else allowed[0]
        else:
            if blocker is not None and same_start.end > blocker.start:
                _note_skipped(skipped, same_start, blocker)
                continue
            chosen = same_start
        if chosen.rule.match_type == "regex":
            budget.note_regex_hit(chosen.rule, chosen.start, fragment_hits)
        spans.append(chosen)
        cursor = chosen.end
        cursor_winner = chosen
    spans.extend(protected[protected_index:])
    return tuple(spans)


def replace_stage(
    text: str,
    rules: tuple[Rule, ...],
    regex_patterns: Mapping[str, object],
    budget: RegexBudget,
    *,
    literal_index: Mapping[str, tuple[Rule, ...]] | None = None,
    order: Mapping[str, int] | None = None,
    skipped: list[SkippedRuleMatch] | None = None,
) -> tuple[str, tuple[StageHit, ...]]:
    """Apply one stage's non-cascading replacements from a single input value."""

    if not rules:
        return text, ()
    if literal_index is not None and order is not None:
        regex_rules = (
            tuple(rule for rule in rules if rule.match_type == "regex")
            if regex_patterns else ()
        )
        candidates = collect_matches(
            text,
            _indexed_stage_candidates(
                text,
                regex_rules,
                literal_index,
                order,
            ),
            regex_patterns,
            budget,
        )
    else:
        candidates = collect_matches(text, rules, regex_patterns, budget)
    by_start: dict[int, RuleMatch | list[RuleMatch]] = {}
    for candidate in candidates:
        previous = by_start.get(candidate.start)
        if previous is None:
            by_start[candidate.start] = candidate
        elif isinstance(previous, list):
            previous.append(candidate)
        else:
            by_start[candidate.start] = [previous, candidate]
    selected = []
    fragment_hits: dict[str, int] = {}
    cursor = 0
    cursor_winner: RuleMatch | None = None
    for start in sorted(by_start):
        if start < cursor:
            _note_skipped(skipped, by_start[start], cursor_winner)
            continue
        same_start = by_start[start]
        chosen = _resolve_same_start(same_start) if isinstance(same_start, list) else same_start
        selected.append(chosen)
        cursor = chosen.end
        cursor_winner = chosen

    output = []
    hits = []
    cursor = 0
    for match in selected:
        output.append(text[cursor:match.start])
        output.append(match.target)
        if match.rule.match_type == "regex":
            budget.note_regex_hit(match.rule, match.start, fragment_hits)
        hits.append(StageHit(match.rule, match.start, match.end,
                             text[match.start:match.end], match.target))
        cursor = match.end
    output.append(text[cursor:])
    return "".join(output), tuple(hits)


__all__ = [
    "REGEX_MATCH_TIMEOUT_SECONDS",
    "REGEX_MAX_RULES",
    "REGEX_MAX_PATTERN_CHARS",
    "REGEX_MAX_HITS_PER_RULE",
    "REGEX_MAX_CANDIDATES_PER_FRAGMENT",
    "REGEX_MAX_CANDIDATE_OUTPUT_CHARS_PER_FRAGMENT",
    "RegexBudget",
    "RuleExecutionError",
    "StageHit",
    "collect_matches",
    "literal_candidates",
    "replace_stage",
    "source_matches",
]
