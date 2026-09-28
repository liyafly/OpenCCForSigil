"""Bounded literal and regular-expression rule matching."""

from __future__ import annotations

from dataclasses import dataclass
import re
import time
from typing import Mapping

from .models import Rule
from .precedence import scope_rank, type_rank


REGEX_MATCH_TIMEOUT_SECONDS = 0.05
REGEX_RUN_BUDGET_SECONDS = 3.0
REGEX_MAX_RULES = 128
REGEX_MAX_PATTERN_CHARS = 512
REGEX_MAX_HITS_PER_RULE = 512
REGEX_MAX_HITS_PER_RUN = 100_000
REGEX_MAX_CANDIDATES_PER_FRAGMENT = 20_000
REGEX_SECONDS_PER_MILLION_CHARS = 2.0
REGEX_MAX_OUTPUT_CHARS_PER_RUN = 2_000_000
REGEX_MAX_CANDIDATE_OUTPUT_CHARS_PER_RUN = 2_000_000


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


class RegexBudget:
    """Cumulative work limit shared by all text targets in one conversion plan."""

    def __init__(self) -> None:
        self.regex_seconds = 0.0
        self.scanned_chars = 0
        self.regex_hits = 0
        self.output_chars = 0
        self.candidate_output_chars = 0

    def allowance(self) -> float:
        return (REGEX_RUN_BUDGET_SECONDS
                + REGEX_SECONDS_PER_MILLION_CHARS * self.scanned_chars / 1_000_000)

    def note_scan(self, length: int) -> None:
        self.scanned_chars += max(0, int(length))

    def timeout_for(self, rule: Rule, position: int) -> float:
        allowance = self.allowance()
        remaining = allowance - self.regex_seconds
        if remaining <= 0:
            raise RuleExecutionError(
                f"rule {rule.id}: regular-expression run exceeded its "
                f"{allowance:g} second budget near offset {position}")
        return min(REGEX_MATCH_TIMEOUT_SECONDS, remaining)

    def note_regex_time(self, rule: Rule, elapsed: float, position: int) -> None:
        self.regex_seconds += max(0.0, elapsed)
        allowance = self.allowance()
        if self.regex_seconds > allowance:
            raise RuleExecutionError(
                f"rule {rule.id}: regular-expression run exceeded its "
                f"{allowance:g} second budget near offset {position}")

    def note_regex_hit(
        self, rule: Rule, position: int, fragment_hits: dict[str, int]
    ) -> None:
        self.regex_hits += 1
        count = fragment_hits.get(rule.id, 0) + 1
        fragment_hits[rule.id] = count
        if count > REGEX_MAX_HITS_PER_RULE:
            raise RuleExecutionError(
                f"rule {rule.id}: regular expression exceeded {REGEX_MAX_HITS_PER_RULE} "
                f"hits near offset {position}")
        if self.regex_hits > REGEX_MAX_HITS_PER_RUN:
            raise RuleExecutionError(
                f"rule {rule.id}: regular-expression rules exceeded "
                f"{REGEX_MAX_HITS_PER_RUN} hits near offset {position}")

    def note_candidate_output(self, rule: Rule, length: int, position: int) -> None:
        if self.candidate_output_chars + length > REGEX_MAX_CANDIDATE_OUTPUT_CHARS_PER_RUN:
            raise RuleExecutionError(
                f"rule {rule.id}: replacement candidate memory exceeded "
                f"{REGEX_MAX_CANDIDATE_OUTPUT_CHARS_PER_RUN} characters near offset {position}")
        self.candidate_output_chars += length

    def note_output(self, rule: Rule, length: int, position: int, *, stage: str) -> None:
        if self.output_chars + length > REGEX_MAX_OUTPUT_CHARS_PER_RUN:
            raise RuleExecutionError(
                f"rule {rule.id}: {stage} replacement output exceeded "
                f"{REGEX_MAX_OUTPUT_CHARS_PER_RUN} characters near offset {position}")
        self.output_chars += length


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
    *,
    include_single_char_rules: bool = True,
) -> tuple[Rule, ...]:
    """Return indexed literal rules whose one/two-character prefix occurs."""

    if include_single_char_rules:
        keys = set(text)
        keys.update(text[position:position + 2] for position in range(len(text) - 1))
    else:
        keys = {text[position:position + 2] for position in range(len(text) - 1)}
    found = [rule for key in keys.intersection(index) for rule in index[key]]
    found.sort(key=lambda rule: order[rule.id])
    return tuple(found)


def _indexed_stage_candidates(
    text: str,
    regex_rules: tuple[Rule, ...],
    literal_index: Mapping[str, tuple[Rule, ...]],
    order: Mapping[str, int],
    *,
    include_single_char_rules: bool = True,
) -> tuple[Rule, ...]:
    literals = literal_candidates(
        text, literal_index, order,
        include_single_char_rules=include_single_char_rules)
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
    regex_scan_noted = False
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

        if not regex_scan_noted:
            budget.note_scan(len(text))
            regex_scan_noted = True
        pattern = regex_patterns.get(rule.id)
        if pattern is None:
            raise RuleExecutionError(f"rule {rule.id}: compiled regular expression is missing")
        cursor = 0
        candidates = 0
        while cursor <= len(text):
            timeout = budget.timeout_for(rule, cursor)
            started = time.monotonic()
            try:
                found = pattern.search(text, cursor, timeout=timeout)
            except TimeoutError as exc:
                budget.note_regex_time(rule, time.monotonic() - started, cursor)
                raise RuleExecutionError(
                    f"rule {rule.id}: regular-expression matching timed out near "
                    f"offset {cursor}") from exc
            except Exception as exc:
                budget.note_regex_time(rule, time.monotonic() - started, cursor)
                raise RuleExecutionError(
                    f"rule {rule.id}: regular-expression matching failed near "
                    f"offset {cursor}: {exc}") from exc
            budget.note_regex_time(rule, time.monotonic() - started, cursor)
            if found is None:
                break
            if found.start() == found.end():
                raise RuleExecutionError(
                    f"rule {rule.id}: zero-length regular-expression match at "
                    f"offset {found.start()} is not allowed")
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
                if upper_bound > REGEX_MAX_CANDIDATE_OUTPUT_CHARS_PER_RUN:
                    raise RuleExecutionError(
                        f"rule {rule.id}: replacement candidate exceeds "
                        f"{REGEX_MAX_CANDIDATE_OUTPUT_CHARS_PER_RUN} characters "
                        f"near offset {found.start()}")
                try:
                    target = found.expand(rule.target)
                except (IndexError, KeyError, ValueError) as exc:
                    raise RuleExecutionError(
                        f"rule {rule.id}: invalid replacement template at "
                        f"offset {found.start()}: {exc}") from exc
                budget.note_candidate_output(rule, len(target), found.start())
            matches.append(RuleMatch(rule, found.start(), found.end(), target))
            # Advancing one code point preserves candidates that overlap this hit.
            cursor = found.start() + 1
    return tuple(matches)


def source_matches(
    text: str,
    rules: tuple[Rule, ...],
    regex_patterns: Mapping[str, object],
    budget: RegexBudget,
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
    for start in sorted(protected_candidates):
        if start < cursor:
            continue
        same_start = protected_candidates[start]
        chosen = _resolve_same_start(same_start) if isinstance(same_start, list) else same_start
        if chosen.rule.match_type == "regex":
            budget.note_regex_hit(chosen.rule, chosen.start, fragment_hits)
        protected.append(chosen)
        cursor = chosen.end

    if not protected:
        spans = []
        cursor = 0
        for start in sorted(override_candidates):
            if start < cursor:
                continue
            same_start = override_candidates[start]
            chosen = _resolve_same_start(same_start) if isinstance(same_start, list) else same_start
            if chosen.rule.match_type == "regex":
                budget.note_regex_hit(chosen.rule, chosen.start, fragment_hits)
            budget.note_output(chosen.rule, len(chosen.target), chosen.start, stage="source")
            spans.append(chosen)
            cursor = chosen.end
        return tuple(spans)

    spans = list(protected)
    cursor = 0
    protected_index = 0
    for start in sorted(override_candidates):
        while protected_index < len(protected) and protected[protected_index].end <= start:
            protected_index += 1
        if start < cursor:
            continue
        same_start = override_candidates[start]
        blocker = (protected[protected_index]
                   if protected_index < len(protected) else None)
        if blocker is not None and blocker.start <= start:
            continue
        candidates_at_start = same_start if isinstance(same_start, list) else [same_start]
        allowed = [candidate for candidate in candidates_at_start
                   if blocker is None or candidate.end <= blocker.start]
        if not allowed:
            continue
        chosen = _resolve_same_start(allowed) if len(allowed) > 1 else allowed[0]
        if chosen.rule.match_type == "regex":
            budget.note_regex_hit(chosen.rule, chosen.start, fragment_hits)
        budget.note_output(chosen.rule, len(chosen.target), chosen.start, stage="source")
        spans.append(chosen)
        cursor = chosen.end
    return tuple(sorted(spans, key=lambda item: (item.start, item.end)))


def replace_stage(
    text: str,
    rules: tuple[Rule, ...],
    regex_patterns: Mapping[str, object],
    budget: RegexBudget,
    *,
    literal_index: Mapping[str, tuple[Rule, ...]] | None = None,
    order: Mapping[str, int] | None = None,
    regex_rules: tuple[Rule, ...] | None = None,
    include_single_char_rules: bool = True,
) -> tuple[str, tuple[StageHit, ...]]:
    """Apply one stage's non-cascading replacements from a single input value."""

    if not rules:
        return text, ()
    if literal_index is not None and order is not None:
        if regex_rules is None:
            regex_rules = tuple(rule for rule in rules if rule.match_type == "regex")
        candidates = collect_matches(
            text,
            _indexed_stage_candidates(
                text,
                regex_rules,
                literal_index,
                order,
                include_single_char_rules=include_single_char_rules,
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
    for start in sorted(by_start):
        if start < cursor:
            continue
        same_start = by_start[start]
        chosen = _resolve_same_start(same_start) if isinstance(same_start, list) else same_start
        selected.append(chosen)
        cursor = chosen.end

    output = []
    hits = []
    cursor = 0
    for match in selected:
        output.append(text[cursor:match.start])
        output.append(match.target)
        if match.rule.match_type == "regex":
            budget.note_regex_hit(match.rule, match.start, fragment_hits)
        budget.note_output(match.rule, len(match.target), match.start,
                           stage=f"{match.rule.stage} stage")
        hits.append(StageHit(match.rule, match.start, match.end,
                             text[match.start:match.end], match.target))
        cursor = match.end
    output.append(text[cursor:])
    return "".join(output), tuple(hits)


__all__ = [
    "REGEX_MATCH_TIMEOUT_SECONDS",
    "REGEX_RUN_BUDGET_SECONDS",
    "REGEX_MAX_RULES",
    "REGEX_MAX_PATTERN_CHARS",
    "REGEX_MAX_HITS_PER_RULE",
    "REGEX_MAX_HITS_PER_RUN",
    "REGEX_MAX_CANDIDATES_PER_FRAGMENT",
    "REGEX_SECONDS_PER_MILLION_CHARS",
    "REGEX_MAX_OUTPUT_CHARS_PER_RUN",
    "RegexBudget",
    "RuleExecutionError",
    "StageHit",
    "collect_matches",
    "literal_candidates",
    "replace_stage",
    "source_matches",
]
