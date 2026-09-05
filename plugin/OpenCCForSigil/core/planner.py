"""Immutable ConversionPlan construction."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from typing import Optional

from core.converter import OfficialBackendConverter
from core.models import ConversionPlan, ConvertRequest, SourceSpan, TextTarget, TokenChange
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
    for target in document.targets:
        if not target.convert:
            continue
        result = converter.convert(target.source_text, request)
        for local_change in result.changes:
            changes.append(_absolute_change(file_id, target, local_change, source))

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
    change_key = "\0".join(
        (file_id, target.node_id, str(start), str(end), local_change.target)
    )
    change_id = sha256(change_key.encode("utf-8")).hexdigest()[:24]
    before_start = max(0, start - 32)
    after_end = min(len(source), end + 32)
    return TokenChange(
        source=local_change.source,
        target=local_change.target,
        span=SourceSpan(start, end),
        rule_source=local_change.rule_source,
        change_id=change_id,
        file_id=file_id,
        target_id=target.node_id,
        category=local_change.category,
        risk="LOW",
        attribution_method=None,
        context_before=source[before_start:start],
        context_after=source[end:after_end],
    )


def _sha256_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


__all__ = ["ConversionPlan", "build_conversion_plan", "plan_not_implemented"]
