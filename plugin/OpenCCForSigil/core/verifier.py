"""Structural and planned-span verification boundary."""

from typing import Iterable, Tuple

from core.models import StagedFile, VerificationResult
from core.staging import StagingError, apply_changes, source_sha256
from document.tokenizer import TokenizerOptions, tokenize_xhtml


def verification_passed(file_id: str) -> VerificationResult:
    """Return a neutral result for an empty staging set."""

    return VerificationResult(file_id=file_id, passed=True)


def verify_staged_file(
    staged_file: StagedFile,
    *,
    tokenizer_options: TokenizerOptions | None = None,
) -> VerificationResult:
    """Verify a staged file before the Sigil adapter is allowed to commit it."""

    diagnostics = []
    plan = staged_file.plan
    if source_sha256(staged_file.original) != plan.source_sha256:
        diagnostics.append("SOURCE_SHA256_MISMATCH")
    try:
        expected = apply_changes(staged_file.original, plan.changes)
    except StagingError as exc:
        diagnostics.append(f"INVALID_PLAN:{exc}")
        expected = None
    if expected is not None and expected != staged_file.converted:
        diagnostics.append("STAGED_CONTENT_MISMATCH")
    try:
        staged_file.converted.encode("utf-8")
    except UnicodeEncodeError:
        diagnostics.append("INVALID_UTF8")

    original_doc = tokenize_xhtml(staged_file.original, tokenizer_options)
    converted_doc = tokenize_xhtml(staged_file.converted, tokenizer_options)
    if original_doc.structural_signature != converted_doc.structural_signature:
        diagnostics.append("XHTML_STRUCTURE_CHANGED")
    if original_doc.protected_attribute_signature() != converted_doc.protected_attribute_signature():
        diagnostics.append("PROTECTED_ATTRIBUTE_CHANGED")

    return VerificationResult(
        file_id=staged_file.file_id,
        passed=not diagnostics,
        diagnostics=tuple(_diagnostic(value) for value in diagnostics),
        checked_change_ids=tuple(change.change_id for change in plan.changes),
    )


def verify_staging(
    staged_files: Iterable[StagedFile],
    *,
    tokenizer_options: TokenizerOptions | None = None,
) -> Tuple[VerificationResult, ...]:
    return tuple(
        verify_staged_file(staged_file, tokenizer_options=tokenizer_options)
        for staged_file in staged_files
    )


def _diagnostic(message: str):
    from core.models import Diagnostic

    return Diagnostic(code=message.split(":", 1)[0], message=message)
