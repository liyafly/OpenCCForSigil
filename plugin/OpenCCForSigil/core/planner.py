"""Immutable ConversionPlan construction."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from html import escape, unescape
from document.diagnostics import inline_boundary_diagnostics
import json
from typing import Optional

from core.converter import OfficialBackendConverter
from core.models import ConversionPlan, ConvertRequest, SourceSpan, TextTarget, TokenChange, ConvertResult
from transforms.language_tags import is_han_language
from document.tokenizer import TokenizedDocument
from opencc_backend.backend import OpenCCBackend


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

    converter = OfficialBackendConverter(backend)
    changes = []
    diagnostics = list(inline_boundary_diagnostics(document)) if document_kind in {"xhtml", "nav"} else []
    for target in document.targets:
        if check_cancel is not None:
            check_cancel()
        if not target.convert:
            continue
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
            converted = converter.convert(decoded, request)
            attribution = (converted.changes[0] if converted.changes else TokenChange(
                source=decoded, target=decoded, span=SourceSpan(0, len(decoded)),
                rule_source="NumericReferenceDecode"))
            result = ConvertResult(target.source_text, converted.target, (replace(
                attribution, source=target.source_text, target=converted.target,
                span=SourceSpan(0, len(target.source_text)), category="numeric_reference", risk="HIGH"),),
                converted.diagnostics)

        else:
            result = converter.convert(target.source_text, request)
        diagnostics.extend(result.diagnostics)
        for local_change in result.changes:
            change = _absolute_change(file_id, target, local_change, source)
            if document_kind == "metadata":
                change = replace(change, risk="HIGH")
            changes.append(replace(change, document_kind=document_kind))

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


def plan_not_implemented() -> None:
    """Retain the old placeholder name without hiding the implemented API."""

    raise NotImplementedError("Use build_conversion_plan(...) to construct a ConversionPlan")


def _absolute_change(
    file_id: str,
    target: TextTarget,
    local_change: TokenChange,
    source: str,
) -> TokenChange:
    start = target.source_start + local_change.span.start
    end = target.source_start + local_change.span.end
    target_text = local_change.target
    in_cdata = (source.rfind("<![CDATA[", 0, start) > source.rfind("]]>", 0, start))
    if in_cdata:
        if "]]>" in target_text:
            raise ValueError("replacement cannot terminate a CDATA section")
    else:
        target_text = escape(target_text, quote=target.attribute_name is not None)
    change_key = "\0".join(
        (file_id, target.node_id, str(start), str(end), target_text)
    )
    change_id = sha256(change_key.encode("utf-8")).hexdigest()[:24]
    before_start = max(0, start - 32)
    after_end = min(len(source), end + 32)
    return TokenChange(
        source=local_change.source,
        target=target_text,
        span=SourceSpan(start, end),
        rule_source=local_change.rule_source,
        change_id=change_id,
        file_id=file_id,
        target_id=target.node_id,
        category=local_change.category,
        risk=local_change.risk,
        attribution_method=local_change.attribution_method,
        comparison_stage=local_change.comparison_stage,
        attribution_confidence=local_change.attribution_confidence,
        context_before=source[before_start:start],
        context_after=source[end:after_end],
        document_kind=target.document_kind,
        group_id=local_change.group_id,
    )


def _sha256_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


__all__ = ["ConversionPlan", "build_conversion_plan", "plan_not_implemented"]
