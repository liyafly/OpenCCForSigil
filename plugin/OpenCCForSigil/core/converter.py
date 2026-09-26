"""Conversion orchestration boundary.

The actual conversion remains in :mod:`opencc_backend`.  This module only
turns one backend result into source-relative changes that a planner can move
to absolute document offsets.
"""

from dataclasses import replace
from hashlib import sha256
import json
from typing import Protocol

from core.diff import bounded_opcodes
from core.models import ConvertRequest, ConvertResult, SourceSpan, TokenChange, Diagnostic
from opencc_backend.backend import OpenCCBackend


class Converter(Protocol):
    def convert(self, text: str, request: ConvertRequest, *, quotation_pairer=None) -> ConvertResult:
        ...


class OfficialBackendConverter:
    """Adapt one official backend instance to the core converter contract."""

    def __init__(self, backend: OpenCCBackend) -> None:
        self.backend = backend
        self._compiled_overlays = {}
        self._regex_budget = None

    def convert(self, text: str, request: ConvertRequest, *, quotation_pairer=None) -> ConvertResult:
        if not isinstance(text, str):
            raise TypeError("conversion input must be text")
        if request.rules_snapshot.rules:
            return self._convert_rules(text, request, quotation_pairer=quotation_pairer)
        from core.classifier import classify_conversion
        from core.diagnostics import diagnose_mixed_script
        from core.transformation import apply_force_pivot
        from transforms.quotations import DOUBLE_QUOTE_CHARACTERS, QuotationPairer
        from transforms.punctuation import normalize_punctuation

        compare = getattr(self.backend, "convert_for_config", None)
        rule_source = f"OpenCC:{request.config}"
        if request.pivot_chain:
            if request.pivot_chain[-1] != request.config:
                raise ValueError("force-pivot must end in the selected configuration")
            pivot = apply_force_pivot(text, request.pivot_chain, self.backend, enabled=True)
            official = pivot.target
            rule_source = pivot.rule_source
        else:
            official = self.backend.convert(text)
        pairer = quotation_pairer
        if pairer is None and request.quotation_mode != "keep":
            pairer = QuotationPairer(request.quotation_mode)
        quoted = pairer.feed(official) if pairer is not None else official
        quotation_offsets = frozenset(
            getattr(pairer, "last_changed_offsets", ()))
        target = normalize_punctuation(quoted, request.punctuation_mode)
        diagnostics = []
        if request.diagnose_mixed and callable(compare) and text:
            diagnosis = diagnose_mixed_script(
                text,
                compare,
                known_output_config=(request.config
                                     if request.config in {"s2t", "t2s"}
                                     and not request.pivot_chain else None),
                known_output=(official
                              if request.config in {"s2t", "t2s"}
                              and not request.pivot_chain else None),
            )
            if diagnosis.status == "mixed":
                diagnostics.append(Diagnostic("MIXED_SCRIPT", diagnosis.warning))
        if target == text:
            return ConvertResult(text, target, diagnostics=tuple(diagnostics))
        classification = {}
        if request.detailed_classification and callable(compare) and not request.pivot_chain:
            result = classify_conversion(text, request.config, compare, final=official)
            classification = {(item.source_start, item.source_end, item.target): item
                              for item in result.changes}
        changes = []
        for tag, i1, i2, j1, j2 in bounded_opcodes(text, target):
            if tag == "equal":
                continue
            source_part, target_part = text[i1:i2], target[j1:j2]
            attribution = classification.get((i1, i2, target_part))
            source_name = rule_source
            category = attribution.category if attribution else _change_category(source_part, target_part)
            attribution_method = attribution.attribution_method if attribution else None
            rewritten_quotes = any(j1 <= offset < j2 for offset in quotation_offsets)
            quote_only_change = (
                rewritten_quotes
                and source_part
                and all(char in DOUBLE_QUOTE_CHARACTERS for char in source_part)
                and len(source_part) == len(target_part)
                and all(offset in quotation_offsets for offset in range(j1, j2))
            )
            if quote_only_change:
                source_name, category = "QuotationTransform", "quotation"
            elif rewritten_quotes:
                method = attribution_method or "OpenCC conversion"
                attribution_method = f"{method}; includes QuotationTransform"
            elif not request.pivot_chain and attribution is None:
                if (request.punctuation_mode != "keep" and
                      normalize_punctuation(source_part, request.punctuation_mode) == target_part):
                    source_name, category = "PunctuationTransform", "punctuation"
            changes.append(TokenChange(
                source=source_part, target=target_part, span=SourceSpan(i1, i2),
                rule_source=source_name, category=category,
                risk=("HIGH" if request.pivot_chain else "REVIEW" if category == "regional" or
                      (attribution and attribution.attribution_confidence == "low") else "LOW"),
                attribution_method=attribution_method,
                comparison_stage=attribution.comparison_stage if attribution else None,
                attribution_confidence=attribution.attribution_confidence if attribution else None,
            ))
        return ConvertResult(text, target, tuple(changes), tuple(diagnostics))

    def _convert_rules(self, text, request, *, quotation_pairer=None):
        from rules.compiled import CompiledOverlay, lock_spans_compiled
        from rules.matching import RuleExecutionError, replace_stage
        from transforms.quotations import QuotationPairer

        rules_hash = request.rules_snapshot.rules_hash
        cache_key = (rules_hash, request.config, request.profile_id,
                     request.book_fingerprint)
        cached = self._compiled_overlays.get(cache_key)
        if cached is not None and cached[0] is request.rules_snapshot.rules:
            overlay = cached[1]
        else:
            overlay = CompiledOverlay.build(
                request.rules_snapshot,
                expected_hash=rules_hash,
                config=request.config,
                profile_id=request.profile_id,
                book_fingerprint=request.book_fingerprint,
            )
            self._compiled_overlays[cache_key] = (request.rules_snapshot.rules, overlay)
        from rules.matching import RegexBudget

        guarded_rules = any(rule.match_type == "regex" or rule.action == "replace"
                            for rule in overlay.rules)
        if guarded_rules and self._regex_budget is None:
            self._regex_budget = RegexBudget()
        budget = self._regex_budget or RegexBudget()
        spans = lock_spans_compiled(text, overlay, budget)
        pairer = quotation_pairer or QuotationPairer(request.quotation_mode)
        # Reuse the complete unlocked pipeline while avoiding a second rule pass.
        unlocked = replace(request, rules_snapshot=type(request.rules_snapshot)())
        output, changes, diagnostics = [], [], []
        regex_patterns = dict(overlay.regex_patterns)
        pre_rules = tuple(rule for rule in overlay.rules if rule.action == "replace" and rule.stage == "pre")
        post_rules = tuple(rule for rule in overlay.rules if rule.action == "replace" and rule.stage == "post")
        cursor = 0
        for span in (*spans, None):
            end = span.start if span is not None else len(text)
            if end > cursor:
                segment = text[cursor:end]
                try:
                    before_opencc, pre_hits = replace_stage(
                        segment, pre_rules, regex_patterns, budget)
                    converted = self.convert(
                        before_opencc, unlocked, quotation_pairer=pairer)
                    final_segment, post_hits = replace_stage(
                        converted.target, post_rules, regex_patterns, budget)
                except RuleExecutionError:
                    raise
                output.append(final_segment)
                changed_pre_hits = tuple(hit for hit in pre_hits if hit.source != hit.target)
                changed_post_hits = tuple(hit for hit in post_hits if hit.source != hit.target)
                if not changed_pre_hits and not changed_post_hits:
                    changes.extend(replace(change, span=SourceSpan(
                        cursor + change.span.start, cursor + change.span.end))
                        for change in converted.changes)
                    diagnostics.extend(converted.diagnostics)
                else:
                    changes.extend(_staged_segment_changes(
                        segment,
                        before_opencc,
                        converted,
                        final_segment,
                        cursor,
                        request.config,
                        changed_pre_hits,
                        changed_post_hits,
                    ))
                    diagnostics.extend(_map_diagnostics(
                        converted.diagnostics,
                        segment,
                        before_opencc,
                    ))
            if span is not None:
                pairer.feed(span.source, mutate=False)
                output.append(span.target)
                if span.source != span.target:
                    changes.append(TokenChange(
                        source=span.source, target=span.target,
                        span=SourceSpan(span.start, span.end),
                        rule_source=f"UserRule:{span.rule.id}", category="user_rule",
                        risk="HIGH" if len(span.source) != len(span.target) else "REVIEW"))
                cursor = span.end
        return ConvertResult(text, "".join(output), tuple(changes), tuple(diagnostics))


def _map_generated_span(source: str, generated: str, start: int, end: int) -> tuple[int, int]:
    """Map one generated-text range back through a bounded source diff."""

    if source == generated:
        return start, end
    mapped = []
    for tag, i1, i2, j1, j2 in bounded_opcodes(source, generated):
        if tag == "equal":
            left, right = max(start, j1), min(end, j2)
            if left < right:
                mapped.append((i1 + left - j1, i1 + right - j1))
            continue
        if j1 == j2:
            if start <= j1 <= end:
                mapped.append((i1, i2))
            continue
        if start < j2 and j1 < end:
            mapped.append((i1, i2))
    if mapped:
        return min(left for left, _right in mapped), max(right for _left, right in mapped)

    boundary = max(0, min(start, len(generated)))
    for tag, i1, i2, j1, j2 in bounded_opcodes(source, generated):
        if tag == "equal" and j1 <= boundary <= j2:
            point = i1 + boundary - j1
            return point, point
        if j1 <= boundary <= j2:
            return i1, i2
    return len(source), len(source)


def _ranges_intersect(left_start: int, left_end: int, right_start: int, right_end: int) -> bool:
    if left_start == left_end:
        return right_start <= left_start <= right_end
    if right_start == right_end:
        return left_start <= right_start <= left_end
    return left_start < right_end and right_start < left_end


def _staged_segment_changes(
    original: str,
    before_opencc: str,
    converted: ConvertResult,
    final: str,
    source_offset: int,
    config: str,
    pre_hits,
    post_hits,
) -> list[TokenChange]:
    """Rebuild final patches against original offsets and retain rule groups."""

    user_hits = []
    for hit in pre_hits:
        user_hits.append((hit.rule, hit.start, hit.end))
    for hit in post_hits:
        start, end = _map_generated_span(
            original, converted.target, hit.start, hit.end)
        user_hits.append((hit.rule, start, end))

    opcodes = bounded_opcodes(original, final)
    changed = [item for item in opcodes if item[0] != "equal"]
    parents = list(range(len(user_hits)))

    def find(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left, right):
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    patch_hits = []
    for _tag, i1, i2, _j1, _j2 in changed:
        related = [index for index, (_rule, start, end) in enumerate(user_hits)
                   if _ranges_intersect(i1, i2, start, end)]
        for index in related[1:]:
            union(related[0], index)
        patch_hits.append(related)

    component_keys = {}
    for index, (rule, start, _end) in enumerate(user_hits):
        component_keys.setdefault(find(index), []).append(
            f"{rule.id}@{source_offset + start}:{source_offset + _end}")
    group_ids = {
        root: "rules:" + sha256(
            json.dumps(sorted(values), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:24]
        for root, values in component_keys.items()
    }

    mapped_conversion = []
    for item in converted.changes:
        start, end = _map_generated_span(
            original, before_opencc, item.span.start, item.span.end)
        mapped_conversion.append((start, end, item))

    changes = []
    for opcode, related in zip(changed, patch_hits):
        _tag, i1, i2, j1, j2 = opcode
        source_part, target_part = original[i1:i2], final[j1:j2]
        if related:
            roots = {find(index) for index in related}
            root = min(roots, key=lambda value: group_ids.get(value, ""))
            rules = sorted({user_hits[index][0].id for index in related})
            rule_source = "UserRule:" + ",".join(rules)
            group_id = group_ids.get(root, "")
            category = "user_rule"
            risk = "HIGH" if len(source_part) != len(target_part) else "REVIEW"
            attribution_method = "staged rule replacement"
        else:
            attribution = next((item for start, end, item in mapped_conversion
                                if _ranges_intersect(i1, i2, start, end)), None)
            rule_source = attribution.rule_source if attribution else f"OpenCC:{config}"
            category = attribution.category if attribution else _change_category(
                source_part, target_part)
            risk = attribution.risk if attribution else "LOW"
            attribution_method = attribution.attribution_method if attribution else None
            group_id = ""
        changes.append(TokenChange(
            source=source_part,
            target=target_part,
            span=SourceSpan(source_offset + i1, source_offset + i2),
            rule_source=rule_source,
            category=category,
            risk=risk,
            attribution_method=attribution_method,
            group_id=group_id,
        ))
    return changes


def _map_diagnostics(diagnostics, source: str, generated: str):
    mapped = []
    for diagnostic in diagnostics:
        span = diagnostic.span
        if span is not None:
            start, end = _map_generated_span(source, generated, span.start, span.end)
            diagnostic = replace(diagnostic, span=SourceSpan(start, end))
        mapped.append(diagnostic)
    return mapped


def _change_category(source: str, target: str) -> str:
    return "character" if max(len(source), len(target)) == 1 else "phrase"
