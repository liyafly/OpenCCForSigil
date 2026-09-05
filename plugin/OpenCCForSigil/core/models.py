"""Stable data contracts shared by the conversion pipeline.

These models intentionally carry source offsets and provenance instead of
holding a parsed/serialized EPUB tree.  The final write boundary is a patch
over the original source string.
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass(frozen=True)
class SourceSpan:
    """An absolute half-open source span in a single source string."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            raise ValueError("SourceSpan must satisfy 0 <= start <= end")


@dataclass(frozen=True)
class TextTarget:
    """A source-preserving text or explicitly allowed attribute target."""

    node_id: str
    source_text: str
    source_start: int
    source_end: int
    context: str = ""
    tag_name: Optional[str] = None
    attribute_name: Optional[str] = None
    document_kind: str = "xhtml"
    convert: bool = True
    skip_reason: Optional[str] = None

    def __post_init__(self) -> None:
        if self.source_start < 0 or self.source_end < self.source_start:
            raise ValueError("TextTarget offsets must satisfy 0 <= start <= end")
        if self.source_end - self.source_start != len(self.source_text):
            raise ValueError("TextTarget source_text must match its source span length")

    @property
    def span(self) -> SourceSpan:
        return SourceSpan(self.source_start, self.source_end)

    @property
    def kind(self) -> str:
        return "attribute" if self.attribute_name is not None else "text"


@dataclass(frozen=True)
class RuleSnapshot:
    """Immutable rule provenance captured when a plan is created."""

    schema_version: int = 1
    rules_hash: str = ""


@dataclass(frozen=True)
class ConvertRequest:
    config: str
    segmentation: str = "mmseg"
    rules_snapshot: RuleSnapshot = field(default_factory=RuleSnapshot)


@dataclass(frozen=True)
class TokenChange:
    source: str
    target: str
    span: SourceSpan
    rule_source: str
    change_id: str = ""
    file_id: str = ""
    target_id: str = ""
    category: str = "opencc_change"
    risk: str = "LOW"
    attribution_method: Optional[str] = None
    context_before: str = ""
    context_after: str = ""


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    span: Optional[SourceSpan] = None


@dataclass(frozen=True)
class ConvertResult:
    source: str
    target: str
    changes: Tuple[TokenChange, ...] = ()
    diagnostics: Tuple[Diagnostic, ...] = ()


@dataclass(frozen=True)
class ConversionPlan:
    """Immutable plan whose allowed spans define the write boundary.

    ``changes`` is the complete set of proposed patches at plan creation.
    Preview decisions create a second plan containing only accepted changes;
    neither operation mutates the original source or the original plan.
    """

    source_sha256: str
    allowed_spans: Tuple[SourceSpan, ...] = ()
    changes: Tuple[TokenChange, ...] = ()
    config: str = "s2t"
    rules_snapshot: RuleSnapshot = field(default_factory=RuleSnapshot)
    session_id: str = ""
    profile_id: str = ""
    file_id: str = ""
    backend_provenance_hash: str = ""
    targets: Tuple[TextTarget, ...] = ()
    source_length: int = 0


@dataclass(frozen=True)
class StagedFile:
    file_id: str
    original: str
    converted: str
    plan: ConversionPlan
    accepted_change_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class VerificationResult:
    file_id: str
    passed: bool
    diagnostics: Tuple[Diagnostic, ...] = ()
    checked_change_ids: Tuple[str, ...] = ()


class ChineseConverter:
    """Structural protocol placeholder for the Phase 1 converter."""

    def convert(self, text: str, request: ConvertRequest) -> ConvertResult:
        raise NotImplementedError
