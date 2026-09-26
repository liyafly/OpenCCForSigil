"""Pure locked-span overlay execution.

The engine receives an official conversion callback.  It never imports
``opencc`` and never mutates a document, which keeps the rule behavior useful
to both the planner and the text-only sandbox.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from core.diff import bounded_opcodes
from .models import Rule, RuleSnapshot
from .matching import RegexBudget, replace_stage


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
class OverlayChange:
    source: str
    target: str
    start: int
    end: int
    rule_source: str
    kind: str = "user_rule"


@dataclass(frozen=True)
class RuleHit:
    rule_id: str
    source: str
    target: str
    start: int
    end: int
    rule_type: str


@dataclass(frozen=True)
class OverlayResult:
    original: str
    after_pre_rules: str
    after_opencc: str
    after_post_rules: str
    final: str
    locked_spans: tuple[LockedSpan, ...] = ()
    changes: tuple[OverlayChange, ...] = ()
    rule_hits: tuple[RuleHit, ...] = ()
    protected_spans: tuple[LockedSpan, ...] = ()

    @property
    def target(self) -> str:
        return self.final

    @property
    def changed(self) -> bool:
        return self.original != self.final

    def reconstruct(self) -> str:
        """Apply source-relative changes to prove they reproduce ``final``."""

        value = self.original
        for change in sorted(self.changes, key=lambda item: (item.start, item.end), reverse=True):
            value = value[: change.start] + change.target + value[change.end :]
        return value


def lock_spans(
    text: str,
    snapshot: RuleSnapshot,
    *,
    config: str,
    profile_id: str | None = None,
    book_fingerprint: str | None = None,
) -> tuple[LockedSpan, ...]:
    """Find non-overlapping exact/protect spans left to right.

    The candidate order encodes the spec's precedence and deterministic
    tie-breakers.  A span consumes its source range, so later rules can never
    match inside or rewrite a user target.
    """

    from .compiled import CompiledOverlay, lock_spans_compiled

    overlay = CompiledOverlay.build(
        snapshot,
        expected_hash=snapshot.rules_hash,
        config=config,
        profile_id=profile_id,
        book_fingerprint=book_fingerprint,
    )
    return lock_spans_compiled(text, overlay)


def convert_with_overlay(
    text: str,
    official_convert: Callable[[str], str] | object,
    *,
    config: str,
    snapshot: RuleSnapshot,
    profile_id: str | None = None,
    book_fingerprint: str | None = None,
) -> OverlayResult:
    """Convert unlocked segments while preserving exact/protect targets."""

    from .compiled import CompiledOverlay, lock_spans_compiled

    overlay = CompiledOverlay.build(
        snapshot,
        expected_hash=snapshot.rules_hash,
        config=config,
        profile_id=profile_id,
        book_fingerprint=book_fingerprint,
    )
    budget = RegexBudget()
    spans = lock_spans_compiled(text, overlay, budget)
    convert = (
        official_convert if callable(official_convert) else getattr(official_convert, "convert")
    )
    output: list[str] = []
    pre_output: list[str] = []
    opencc_output: list[str] = []
    changes: list[OverlayChange] = []
    hits: list[RuleHit] = []
    protected: list[LockedSpan] = []
    regex_patterns = dict(overlay.regex_patterns)
    pre_rules = tuple(rule for rule in overlay.rules
                      if rule.action == "replace" and rule.stage == "pre")
    post_rules = tuple(rule for rule in overlay.rules
                       if rule.action == "replace" and rule.stage == "post")
    cursor = 0
    for span in spans:
        if cursor < span.start:
            segment = text[cursor:span.start]
            before_opencc, pre_hits = replace_stage(
                segment, pre_rules, regex_patterns, budget)
            converted = _converted_text(convert, before_opencc)
            final, post_hits = replace_stage(converted, post_rules, regex_patterns, budget)
            pre_output.append(before_opencc)
            opencc_output.append(converted)
            output.append(final)
            changes.extend(_overlay_segment_changes(
                segment, final, cursor, config,
                has_rule_hits=bool(pre_hits or post_hits)))
            hits.extend(_stage_rule_hits(pre_hits, cursor))
            hits.extend(_stage_rule_hits(
                post_hits, cursor, original=segment, generated=converted))
        pre_output.append(span.target)
        opencc_output.append(span.target)
        output.append(span.target)
        hits.append(RuleHit(span.rule.id, span.source, span.target, span.start, span.end,
                            span.rule.action or span.rule.type))
        if span.rule.type == "protect":
            protected.append(span)
        elif span.source != span.target:
            changes.append(
                OverlayChange(
                    span.source, span.target, span.start, span.end, f"UserRule:{span.rule.id}"
                )
            )
        cursor = span.end
    if cursor < len(text):
        segment = text[cursor:]
        before_opencc, pre_hits = replace_stage(segment, pre_rules, regex_patterns, budget)
        converted = _converted_text(convert, before_opencc)
        final, post_hits = replace_stage(converted, post_rules, regex_patterns, budget)
        pre_output.append(before_opencc)
        opencc_output.append(converted)
        output.append(final)
        changes.extend(_overlay_segment_changes(
            segment, final, cursor, config,
            has_rule_hits=bool(pre_hits or post_hits)))
        hits.extend(_stage_rule_hits(pre_hits, cursor))
        hits.extend(_stage_rule_hits(post_hits, cursor, original=segment, generated=converted))
    after_pre = "".join(pre_output)
    after_opencc = "".join(opencc_output)
    final = "".join(output)
    return OverlayResult(
        original=text,
        after_pre_rules=after_pre,
        after_opencc=after_opencc,
        after_post_rules=final,
        final=final,
        locked_spans=spans,
        changes=tuple(
            sorted(
                changes, key=lambda item: (item.start, item.end, item.rule_source)
            )
        ),
        rule_hits=tuple(hits),
        protected_spans=tuple(protected),
    )


def _overlay_segment_changes(
    source: str,
    target: str,
    source_offset: int,
    config: str,
    *,
    has_rule_hits: bool,
) -> list[OverlayChange]:
    if not has_rule_hits:
        return _segment_changes(source, target, source_offset, config)
    return [
        OverlayChange(
            source[i1:i2], target[j1:j2], source_offset + i1, source_offset + i2,
            "UserRule" if source[i1:i2] != target[j1:j2] else f"OpenCC:{config}",
            "user_rule" if source[i1:i2] != target[j1:j2] else "opencc_change",
        )
        for tag, i1, i2, j1, j2 in bounded_opcodes(source, target)
        if tag != "equal"
    ]


def _stage_rule_hits(hits, source_offset, *, original=None, generated=None):
    result = []
    for hit in hits:
        start, end = hit.start, hit.end
        if original is not None and generated is not None:
            start, end = _generated_span_to_source(original, generated, start, end)
        result.append(RuleHit(
            hit.rule.id, hit.source, hit.target,
            source_offset + start, source_offset + end,
            hit.rule.action or hit.rule.type,
        ))
    return result


def _generated_span_to_source(source, generated, start, end):
    if source == generated:
        return start, end
    mapped = []
    for tag, i1, i2, j1, j2 in bounded_opcodes(source, generated):
        if tag == "equal":
            left, right = max(start, j1), min(end, j2)
            if left < right:
                mapped.append((i1 + left - j1, i1 + right - j1))
        elif j1 == j2 and start <= j1 <= end:
            mapped.append((i1, i2))
        elif start < j2 and j1 < end:
            mapped.append((i1, i2))
    if mapped:
        return min(left for left, _right in mapped), max(right for _left, right in mapped)
    return len(source), len(source)


def _converted_text(convert: Callable[[str], str], source: str) -> str:
    target = convert(source)
    if not isinstance(target, str):
        raise TypeError(
            f"official conversion callback must return str, got {type(target).__name__}"
        )
    return target


def _segment_changes(
    source: str, target: str, source_offset: int, config: str
) -> list[OverlayChange]:
    changes: list[OverlayChange] = []
    for tag, i1, i2, j1, j2 in bounded_opcodes(source, target):
        if tag == "equal":
            continue
        changes.append(
            OverlayChange(
                source[i1:i2],
                target[j1:j2],
                source_offset + i1,
                source_offset + i2,
                f"OpenCC:{config}",
                "opencc_change",
            )
        )
    return changes


class RuleEngine:
    """Small state-free facade for callers that prefer an object API."""

    def __init__(self, snapshot: RuleSnapshot) -> None:
        self.snapshot = snapshot

    def lock(
        self,
        text: str,
        *,
        config: str,
        profile_id: str | None = None,
        book_fingerprint: str | None = None,
    ) -> tuple[LockedSpan, ...]:
        return lock_spans(
            text,
            self.snapshot,
            config=config,
            profile_id=profile_id,
            book_fingerprint=book_fingerprint,
        )

    def convert(
        self,
        text: str,
        official_convert: Callable[[str], str] | object,
        *,
        config: str,
        profile_id: str | None = None,
        book_fingerprint: str | None = None,
    ) -> OverlayResult:
        return convert_with_overlay(
            text,
            official_convert,
            config=config,
            snapshot=self.snapshot,
            profile_id=profile_id,
            book_fingerprint=book_fingerprint,
        )


__all__ = [
    "LockedSpan",
    "OverlayChange",
    "OverlayResult",
    "RuleEngine",
    "RuleHit",
    "convert_with_overlay",
    "lock_spans",
]
