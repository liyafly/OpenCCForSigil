"""Structural and planned-span verification boundary."""

from core.models import StagedFile, VerificationResult
from core.staging import StagingError, apply_changes, source_sha256
from document.tokenizer import TokenizedDocument, TokenizerOptions, tokenize_xhtml
from document.xml_processor import tokenize_xml
from document.validation import validate_xhtml_syntax


def verify_staged_file(
    staged_file: StagedFile,
    *,
    tokenizer_options: TokenizerOptions | None = None,
    original_document: TokenizedDocument | None = None,
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

    def tokenize(source):
        if plan.document_kind in {"ncx", "metadata"}:
            return tokenize_xml(source, document_kind=plan.document_kind)
        return tokenize_xhtml(source, tokenizer_options)

    if original_document is None or original_document.source != staged_file.original:
        original_doc = tokenize(staged_file.original)
    else:
        # The workflow already tokenized the immutable source while building
        # the plan. Reuse that document and tokenize only the staged output.
        original_doc = original_document
    converted_doc = tokenize(staged_file.converted)
    if plan.document_kind in {"xhtml", "nav"}:
        try:
            validate_xhtml_syntax(staged_file.converted)
        except ValueError as exc:
            diagnostics.append(f"INVALID_XHTML:{exc}")
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


def _diagnostic(message: str):
    from core.models import Diagnostic

    return Diagnostic(code=message.split(":", 1)[0], message=message)
