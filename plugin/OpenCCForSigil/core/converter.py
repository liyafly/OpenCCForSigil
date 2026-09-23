"""Conversion orchestration boundary.

The actual conversion remains in :mod:`opencc_backend`.  This module only
turns one backend result into source-relative changes that a planner can move
to absolute document offsets.
"""

from dataclasses import replace
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
        spans = lock_spans_compiled(text, overlay)
        pairer = quotation_pairer or QuotationPairer(request.quotation_mode)
        # Reuse the complete unlocked pipeline while avoiding a second rule pass.
        unlocked = replace(request, rules_snapshot=type(request.rules_snapshot)())
        output, changes, diagnostics = [], [], []
        cursor = 0
        for span in (*spans, None):
            end = span.start if span is not None else len(text)
            if end > cursor:
                result = self.convert(text[cursor:end], unlocked, quotation_pairer=pairer)
                output.append(result.target)
                changes.extend(replace(change, span=SourceSpan(
                    cursor + change.span.start, cursor + change.span.end))
                    for change in result.changes)
                diagnostics.extend(result.diagnostics)
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


def _change_category(source: str, target: str) -> str:
    return "character" if max(len(source), len(target)) == 1 else "phrase"
