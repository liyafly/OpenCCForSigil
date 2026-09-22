"""Pure locked-span overlay execution.

The engine receives an official conversion callback.  It never imports
``opencc`` and never mutates a document, which keeps the rule behavior useful
to both the planner and the text-only sandbox.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from core.diff import bounded_opcodes
from .conflicts import BlockingRuleConflict, validate_no_blocking_conflicts
from .models import Rule, RuleSnapshot
from .precedence import applies_to, ordered_rules
from .validators import validate_snapshot


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

    validate_snapshot(snapshot)
    conflicts = validate_no_blocking_conflicts(snapshot.rules)
    if any(conflict.blocking for conflict in conflicts):
        raise BlockingRuleConflict(tuple(conflict for conflict in conflicts if conflict.blocking))
    candidates = ordered_rules(
        rule
        for rule in snapshot.rules
        if applies_to(rule, config=config, profile_id=profile_id, book_fingerprint=book_fingerprint)
    )
    spans: list[LockedSpan] = []
    cursor = 0
    while cursor < len(text):
        match: Rule | None = None
        for rule in candidates:
            if text.startswith(rule.source, cursor):
                match = rule
                break
        if match is None:
            cursor += 1
            continue
        end = cursor + len(match.source)
        target = match.source if match.type == "protect" else match.target
        spans.append(LockedSpan(cursor, end, match.source, target, match))
        cursor = end
    return tuple(spans)


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

    spans = lock_spans(
        text,
        snapshot,
        config=config,
        profile_id=profile_id,
        book_fingerprint=book_fingerprint,
    )
    convert = (
        official_convert if callable(official_convert) else getattr(official_convert, "convert")
    )
    output: list[str] = []
    pre_output: list[str] = []
    changes: list[OverlayChange] = []
    opencc_changes: list[OverlayChange] = []
    hits: list[RuleHit] = []
    protected: list[LockedSpan] = []
    cursor = 0
    for span in spans:
        if cursor < span.start:
            untouched = text[cursor : span.start]
            pre_output.append(untouched)
            converted = _converted_text(convert, untouched)
            output.append(converted)
            opencc_changes.extend(_segment_changes(untouched, converted, cursor, config))
        pre_output.append(span.target)
        output.append(span.target)
        hits.append(
            RuleHit(span.rule.id, span.source, span.target, span.start, span.end, span.rule.type)
        )
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
        untouched = text[cursor:]
        pre_output.append(untouched)
        converted = _converted_text(convert, untouched)
        output.append(converted)
        opencc_changes.extend(_segment_changes(untouched, converted, cursor, config))
    after_pre = "".join(pre_output)
    after_opencc = "".join(output)
    # Regex rules are intentionally unavailable in V1, so post-opencc is a
    # separate named stage with the same immutable value for sandbox clarity.
    return OverlayResult(
        original=text,
        after_pre_rules=after_pre,
        after_opencc=after_opencc,
        after_post_rules=after_opencc,
        final=after_opencc,
        locked_spans=spans,
        changes=tuple(
            sorted(
                changes + opencc_changes, key=lambda item: (item.start, item.end, item.rule_source)
            )
        ),
        rule_hits=tuple(hits),
        protected_spans=tuple(protected),
    )


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


# Readable aliases used by callers that describe the operation as applying an
# overlay rather than converting with one.
apply_overlay = convert_with_overlay
match_locked_spans = lock_spans
convert_text = convert_with_overlay


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
    "apply_overlay",
    "convert_with_overlay",
    "convert_text",
    "lock_spans",
    "match_locked_spans",
]
