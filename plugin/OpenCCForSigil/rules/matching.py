"""Bounded literal and regular-expression rule matching."""

from __future__ import annotations

from dataclasses import dataclass
import re
import time

from .models import Rule
from .precedence import scope_rank, type_rank


REGEX_MATCH_TIMEOUT_SECONDS = 0.05
REGEX_RUN_BUDGET_SECONDS = 3.0
REGEX_MAX_RULES = 128
REGEX_MAX_PATTERN_CHARS = 512
REGEX_MAX_HITS_PER_RULE = 512
REGEX_MAX_HITS_PER_RUN = 4096
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
        self.regex_hits = 0
        self.output_chars = 0
        self.candidate_output_chars = 0
        self._hits_by_rule: dict[str, int] = {}

    def timeout_for(self, rule: Rule, position: int) -> float:
        remaining = REGEX_RUN_BUDGET_SECONDS - self.regex_seconds
        if remaining <= 0:
            raise RuleExecutionError(
                f"rule {rule.id}: regular-expression run exceeded its "
                f"{REGEX_RUN_BUDGET_SECONDS:g} second budget near offset {position}")
        return min(REGEX_MATCH_TIMEOUT_SECONDS, remaining)

    def note_regex_time(self, rule: Rule, elapsed: float, position: int) -> None:
        self.regex_seconds += max(0.0, elapsed)
        if self.regex_seconds > REGEX_RUN_BUDGET_SECONDS:
            raise RuleExecutionError(
                f"rule {rule.id}: regular-expression run exceeded its "
                f"{REGEX_RUN_BUDGET_SECONDS:g} second budget near offset {position}")

    def note_regex_hit(self, rule: Rule, position: int) -> None:
        self.regex_hits += 1
        count = self._hits_by_rule.get(rule.id, 0) + 1
        self._hits_by_rule[rule.id] = count
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


def _rank(match: RuleMatch) -> tuple[int, int, int, int, int]:
    rule = match.rule
    return (type_rank(rule), rule.semantic_version, scope_rank(rule),
            match.end - match.start, int(rule.priority))


def _resolve_same_start(candidates: list[RuleMatch]) -> RuleMatch:
    best_rank = max(_rank(candidate) for candidate in candidates)
    best = [candidate for candidate in candidates if _rank(candidate) == best_rank]
    targets = {candidate.target for candidate in best}
    if len(targets) > 1:
        ids = ", ".join(sorted(candidate.rule.id for candidate in best))
        raise RuleExecutionError(
            f"rules {ids} have the same precedence and different outputs at "
            f"offset {best[0].start}")
    return min(best, key=lambda candidate: candidate.rule.id)


def collect_matches(
    text: str,
    rules: tuple[Rule, ...],
    regex_patterns: dict[str, object],
    budget: RegexBudget,
) -> tuple[RuleMatch, ...]:
    """Collect candidates from one immutable stage input; matches may overlap."""

    matches: list[RuleMatch] = []
    for rule in rules:
        if rule.match_type == "literal":
            cursor = 0
            while rule.source and cursor <= len(text) - len(rule.source):
                start = text.find(rule.source, cursor)
                if start < 0:
                    break
                end = start + len(rule.source)
                target = text[start:end] if rule.action == "protect" else rule.target
                matches.append(RuleMatch(rule, start, end, target))
                cursor = start + 1
            continue

        pattern = regex_patterns.get(rule.id)
        if pattern is None:
            raise RuleExecutionError(f"rule {rule.id}: compiled regular expression is missing")
        cursor = 0
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
            budget.note_regex_hit(rule, found.start())
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
    regex_patterns: dict[str, object],
    budget: RegexBudget,
) -> tuple[RuleMatch, ...]:
    """Reserve protections first, then choose final-wording matches."""

    candidates = collect_matches(text, rules, regex_patterns, budget)
    protected_candidates: dict[int, list[RuleMatch]] = {}
    override_candidates: dict[int, list[RuleMatch]] = {}
    for candidate in candidates:
        bucket = protected_candidates if candidate.rule.action == "protect" else override_candidates
        bucket.setdefault(candidate.start, []).append(candidate)

    protected = []
    cursor = 0
    for start in sorted(protected_candidates):
        if start < cursor:
            continue
        chosen = _resolve_same_start(protected_candidates[start])
        protected.append(chosen)
        cursor = chosen.end

    spans = list(protected)
    cursor = 0
    protected_index = 0
    for start in sorted(override_candidates):
        while protected_index < len(protected) and protected[protected_index].end <= start:
            protected_index += 1
        if start < cursor:
            continue
        chosen = _resolve_same_start(override_candidates[start])
        if (protected_index < len(protected)
                and protected[protected_index].start < chosen.end):
            continue
        budget.note_output(chosen.rule, len(chosen.target), chosen.start, stage="source")
        spans.append(chosen)
        cursor = chosen.end
    return tuple(sorted(spans, key=lambda item: (item.start, item.end)))


def replace_stage(
    text: str,
    rules: tuple[Rule, ...],
    regex_patterns: dict[str, object],
    budget: RegexBudget,
) -> tuple[str, tuple[StageHit, ...]]:
    """Apply one stage's non-cascading replacements from a single input value."""

    if not rules:
        return text, ()
    candidates = collect_matches(text, rules, regex_patterns, budget)
    by_start: dict[int, list[RuleMatch]] = {}
    for candidate in candidates:
        by_start.setdefault(candidate.start, []).append(candidate)
    selected = []
    cursor = 0
    for start in sorted(by_start):
        if start < cursor:
            continue
        chosen = _resolve_same_start(by_start[start])
        selected.append(chosen)
        cursor = chosen.end

    output = []
    hits = []
    cursor = 0
    for match in selected:
        output.append(text[cursor:match.start])
        output.append(match.target)
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
    "REGEX_MAX_OUTPUT_CHARS_PER_RUN",
    "RegexBudget",
    "RuleExecutionError",
    "StageHit",
    "collect_matches",
    "replace_stage",
    "source_matches",
]
