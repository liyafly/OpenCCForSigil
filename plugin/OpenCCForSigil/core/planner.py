"""Immutable ConversionPlan construction."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from html import unescape
import re
from document.diagnostics import inline_boundary_diagnostics
import json
from bisect import bisect_right
from typing import Optional

from core.converter import OfficialBackendConverter
from core.models import (ConversionPlan, ConvertRequest, Diagnostic, SourceSpan, TextTarget,
                         TokenChange, ConvertResult)
from transforms.language_tags import is_han_language
from document.tokenizer import TokenizedDocument
from opencc_backend.backend import OpenCCBackend
from transforms.quotations import DOUBLE_QUOTE_CHARACTERS, QuotationPairer


_BLOCK_LEVEL_ELEMENTS = frozenset(
    "p div li h1 h2 h3 h4 h5 h6 blockquote td th dd dt figcaption section article "
    "aside header footer body".split()
)
_ENTITY_REFERENCE = re.compile(r"&[^;\s<>&]+;")


def build_conversion_plan(
    *,
    file_id: str,
    source: str,
    document: TokenizedDocument,
    backend: OpenCCBackend,
    request: ConvertRequest,
    session_id: str = "",
    profile_id: str = "",
    rules_snapshot_hash: Optional[str] = None,
    document_kind: str = "xhtml",
    check_cancel=None,
    converter: Optional[OfficialBackendConverter] = None,
) -> ConversionPlan:
    """Analyze writable targets and freeze their official OpenCC patches.

    Backend output is computed once while the plan is built. Preview and Apply
    consume these frozen patches; they never call OpenCC again.
    """

    if document.source != source:
        raise ValueError("tokenized document does not belong to source")
    if request.config != backend.config:
        raise ValueError(
            f"backend config {backend.config!r} does not match request {request.config!r}"
        )

    converter = converter or OfficialBackendConverter(backend)
    changes = []
    diagnostics = list(inline_boundary_diagnostics(document)) if document_kind in {"xhtml", "nav"} else []
    block_tags = tuple(tag for tag in document.tags if tag.name.lower() in _BLOCK_LEVEL_ELEMENTS)
    block_tag_ends = tuple(tag.end for tag in block_tags)
    ignored_quote_ranges = _ignored_quotation_ranges(source, document.tags)
    ignored_quote_starts = tuple(start for start, _end in ignored_quote_ranges)
    attribute_spans = tuple(sorted(
        (attribute.value_start, attribute.value_end, tag_index, attribute_index, attribute.name)
        for tag_index, tag in enumerate(document.tags)
        for attribute_index, attribute in enumerate(tag.attributes)
    ))
    attribute_starts = tuple(item[0] for item in attribute_spans)
    cdata_ranges = _cdata_content_ranges(source)
    cdata_starts = tuple(start for start, _end in cdata_ranges)
    block_pairers: dict[int, QuotationPairer] = {}
    block_quote_change_ids: dict[int, list[str]] = {}
    block_spans: dict[int, SourceSpan] = {}
    block_quote_cursors: dict[int, int] = {}
    attribute_pairers: dict[tuple[int, int], QuotationPairer] = {}
    for target in document.targets:
        if check_cancel is not None:
            check_cancel()
        if not target.convert:
            continue
        pairer = None
        block_index = None
        if document_kind in {"xhtml", "nav"} and target.attribute_name is None:
            block_index = bisect_right(block_tag_ends, target.source_start)
            pairer = block_pairers.setdefault(
                block_index, QuotationPairer(request.quotation_mode))
            prior = block_spans.get(block_index)
            block_spans[block_index] = SourceSpan(
                min(prior.start, target.source_start) if prior else target.source_start,
                max(prior.end, target.source_end) if prior else target.source_end,
            )
        elif target.attribute_name is not None:
            position = bisect_right(attribute_starts, target.source_start) - 1
            if position >= 0:
                start, end, tag_index, attribute_index, name = attribute_spans[position]
                if (name == target.attribute_name and start <= target.source_start
                        and target.source_end <= end):
                    pairer = attribute_pairers.setdefault(
                        (tag_index, attribute_index), QuotationPairer(request.quotation_mode))
        if pairer is None:
            # NCX and metadata targets, along with unmatched attribute spans,
            # intentionally keep their quote-pairing state local to one target.
            pairer = QuotationPairer(request.quotation_mode)
        if block_index is not None:
            cursor = block_quote_cursors.get(
                block_index,
                block_tag_ends[block_index - 1] if block_index else 0,
            )
            if request.quotation_mode != "keep":
                _feed_quotation_entities(
                    pairer, source, cursor, target.source_start,
                    ignored_quote_ranges, ignored_quote_starts)
            block_quote_cursors[block_index] = target.source_end
        if target.attribute_name in {"lang", "xml:lang"} or target.tag_name == "dc:language":
            if not request.language_tag or not is_han_language(target.source_text):
                continue
            if target.source_text.strip() == request.language_tag:
                continue
            # Preserve surrounding whitespace in dc:language text.
            leading = len(target.source_text) - len(target.source_text.lstrip())
            trailing = len(target.source_text.rstrip())
            language_change = TokenChange(
                source=target.source_text[leading:trailing], target=request.language_tag,
                span=SourceSpan(leading, trailing), rule_source="language_metadata",
                category="language_metadata", risk="HIGH", group_id="language_metadata",
            )
            result = ConvertResult(target.source_text, request.language_tag, (language_change,))
        elif target.node_id.startswith("numeric_ref:"):
            decoded = unescape(target.source_text)
            converted = converter.convert(decoded, request, quotation_pairer=pairer)
            attribution = (converted.changes[0] if converted.changes else TokenChange(
                source=decoded, target=decoded, span=SourceSpan(0, len(decoded)),
                rule_source="NumericReferenceDecode"))
            result = ConvertResult(target.source_text, converted.target, (replace(
                attribution, source=target.source_text, target=converted.target,
                span=SourceSpan(0, len(target.source_text)), category="numeric_reference", risk="HIGH"),),
                converted.diagnostics)

        else:
            result = converter.convert(target.source_text, request, quotation_pairer=pairer)
        diagnostics.extend(result.diagnostics)
        for local_change in result.changes:
            change = _absolute_change(
                file_id, target, local_change, source,
                cdata_ranges=cdata_ranges, cdata_starts=cdata_starts,
                document_kind=document_kind,
                risk_override="HIGH" if document_kind == "metadata" else None,
            )
            changes.append(change)
            if block_index is not None and (
                change.category == "quotation"
                or "includes QuotationTransform" in (change.attribution_method or "")
            ):
                block_quote_change_ids.setdefault(block_index, []).append(change.change_id)

    for index, cursor in block_quote_cursors.items():
        block_end = block_tags[index].start if index < len(block_tags) else len(source)
        if request.quotation_mode != "keep":
            _feed_quotation_entities(
                block_pairers[index], source, cursor, block_end,
                ignored_quote_ranges, ignored_quote_starts)

    if request.quotation_mode != "keep":
        unbalanced_blocks = {
            index for index, pairer in block_pairers.items() if pairer.ascii_unbalanced
        }
        if unbalanced_blocks:
            unbalanced_change_ids = {
                change_id for index in unbalanced_blocks
                for change_id in block_quote_change_ids.get(index, ())
            }
            changes = [replace(change, risk="REVIEW")
                       if change.change_id in unbalanced_change_ids else change
                       for change in changes]
            diagnostics.extend(
                Diagnostic(
                    "QUOTE_UNBALANCED",
                    "Block contains an unbalanced ASCII quotation mark",
                    block_spans.get(index),
                )
                for index in sorted(unbalanced_blocks)
            )

    boundaries = [item.span for item in diagnostics if item.code == "INLINE_BOUNDARY" and item.span]
    before_boundaries = {span.start for span in boundaries}
    after_boundaries = {span.end for span in boundaries}
    changes = [replace(change, risk="REVIEW") if change.risk != "HIGH" and (
        change.span.end in before_boundaries or change.span.start in after_boundaries)
        else change for change in changes]
    provenance = backend.provenance().as_dict()
    provenance_hash = sha256(
        json.dumps(provenance, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    frozen_rules_hash = rules_snapshot_hash or request.rules_snapshot.rules_hash
    snapshot = request.rules_snapshot
    if frozen_rules_hash and snapshot.rules_hash != frozen_rules_hash:
        snapshot = replace(snapshot, rules_hash=frozen_rules_hash)
    return ConversionPlan(
        source_sha256=_sha256_text(source),
        allowed_spans=tuple(change.span for change in changes),
        changes=tuple(changes),
        config=request.config,
        rules_snapshot=snapshot,
        session_id=session_id,
        profile_id=profile_id,
        file_id=file_id,
        backend_provenance_hash=provenance_hash,
        targets=tuple(document.targets),
        source_length=len(source),
        document_kind=document_kind,
        diagnostics=tuple(diagnostics),
    )


def _ignored_quotation_ranges(source, tags):
    ranges = [(tag.start, tag.end) for tag in tags]
    ranges.extend((match.start(), match.end()) for match in re.finditer(
        r"<!--.*?-->|<!\[CDATA\[.*?\]\]>", source, flags=re.DOTALL))
    protected_names = {"script", "style", "code", "pre", "svg", "math"}
    stack = []
    for tag in tags:
        local_name = tag.name.rsplit(":", 1)[-1]
        if local_name not in protected_names:
            continue
        if tag.closing:
            match_index = next((index for index in range(len(stack) - 1, -1, -1)
                                if stack[index][0] == local_name), None)
            if match_index is not None:
                _name, content_start = stack.pop(match_index)
                ranges.append((content_start, tag.start))
        elif not tag.self_closing:
            stack.append((local_name, tag.end))
    ranges.extend((start, len(source)) for _name, start in stack)
    ranges.sort()
    merged = []
    for start, end in ranges:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(merged)


def _feed_quotation_entities(pairer, source, start, end, ignored_ranges, ignored_starts):
    if start >= end:
        return
    for match in _ENTITY_REFERENCE.finditer(source, start, end):
        position = match.start()
        index = bisect_right(ignored_starts, position) - 1
        if index >= 0 and position < ignored_ranges[index][1]:
            continue
        decoded = unescape(match.group())
        if len(decoded) == 1 and decoded in DOUBLE_QUOTE_CHARACTERS:
            pairer.feed(decoded, mutate=False)


def _cdata_content_ranges(source: str) -> tuple[tuple[int, int], ...]:
    """Find CDATA content spans once so each patch can query them by bisect."""

    ranges = []
    cursor = 0
    while cursor < len(source):
        comment_start = source.find("<!--", cursor)
        cdata_start = source.find("<![CDATA[", cursor)
        if comment_start >= 0 and (cdata_start < 0 or comment_start < cdata_start):
            comment_end = source.find("-->", comment_start + 4)
            if comment_end < 0:
                break
            cursor = comment_end + 3
            continue
        if cdata_start < 0:
            break
        content_start = cdata_start + len("<![CDATA[")
        content_end = source.find("]]>", content_start)
        if content_end < 0:
            ranges.append((content_start, len(source)))
            break
        ranges.append((content_start, content_end))
        cursor = content_end + len("]]>")
    return tuple(ranges)


def _absolute_change(
    file_id: str,
    target: TextTarget,
    local_change: TokenChange,
    source: str,
    *,
    cdata_ranges: Optional[tuple[tuple[int, int], ...]] = None,
    cdata_starts: Optional[tuple[int, ...]] = None,
    document_kind: str,
    risk_override: Optional[str] = None,
) -> TokenChange:
    start = target.source_start + local_change.span.start
    end = target.source_start + local_change.span.end
    patch_end = end
    change_source = local_change.source
    target_text = local_change.target
    if cdata_ranges is None:
        cdata_ranges = _cdata_content_ranges(source)
        cdata_starts = tuple(range_start for range_start, _range_end in cdata_ranges)
    elif cdata_starts is None:
        cdata_starts = tuple(range_start for range_start, _range_end in cdata_ranges)
    cdata_index = bisect_right(cdata_starts, start) - 1
    in_cdata = cdata_index >= 0 and start < cdata_ranges[cdata_index][1]
    if in_cdata:
        if "]]>" in target_text:
            raise ValueError("replacement cannot terminate a CDATA section")
    else:
        target_text = _escape_replacement(target_text, target)
        if target.attribute_name is None:
            if start >= 2 and source[start - 2:start] == "]]" and target_text.startswith(">"):
                target_text = "&gt;" + target_text[1:]
            if target_text.endswith("]]") and source[end:end + 1] == ">":
                # Include the unchanged delimiter in this patch and serialize it
                # as an entity so reconstruction never contains the forbidden sequence.
                target_text += "&gt;"
                patch_end += 1
                change_source += ">"
    change_key = "\0".join(
        (file_id, target.node_id, str(start), str(patch_end), target_text)
    )
    change_id = sha256(change_key.encode("utf-8")).hexdigest()[:24]
    before_start = max(0, start - 32)
    after_end = min(len(source), patch_end + 32)
    text_start = local_change.span.start
    text_end = local_change.span.end
    text_before_start = max(0, text_start - 20)
    text_after_end = min(len(target.source_text), text_end + 20)
    text_context_before = target.source_text[text_before_start:text_start]
    text_context_after = target.source_text[text_end:text_after_end]
    if text_before_start:
        text_context_before = "…" + text_context_before
    if text_after_end < len(target.source_text):
        text_context_after += "…"
    return TokenChange(
        source=change_source,
        target=target_text,
        span=SourceSpan(start, patch_end),
        rule_source=local_change.rule_source,
        change_id=change_id,
        file_id=file_id,
        target_id=target.node_id,
        category=local_change.category,
        risk=risk_override or local_change.risk,
        attribution_method=local_change.attribution_method,
        comparison_stage=local_change.comparison_stage,
        attribution_confidence=local_change.attribution_confidence,
        context_before=source[before_start:start],
        context_after=source[patch_end:after_end],
        text_context_before=text_context_before,
        text_context_after=text_context_after,
        document_kind=document_kind,
        group_id=local_change.group_id,
    )


def _escape_replacement(text: str, target: TextTarget) -> str:
    """Escape only characters that are significant in this source context."""

    escaped = text.replace("&", "&amp;").replace("<", "&lt;")
    if target.attribute_name is not None:
        if target.attribute_quote == '"':
            return escaped.replace('"', "&quot;")
        if target.attribute_quote == "'":
            return escaped.replace("'", "&#x27;")
        # A malformed/unquoted attribute has no delimiter to rely on.
        return escaped.replace('"', "&quot;").replace("'", "&#x27;")
    return escaped.replace("]]>", "]]&gt;")


def _sha256_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


__all__ = ["ConversionPlan", "build_conversion_plan"]
