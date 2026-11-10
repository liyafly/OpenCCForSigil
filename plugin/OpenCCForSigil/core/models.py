"""Stable data contracts shared by the conversion pipeline.

These models intentionally carry source offsets and provenance instead of
holding a parsed/serialized EPUB tree.  The final write boundary is a patch
over the original source string.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
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
    tag_name: str | None = None
    attribute_name: str | None = None
    attribute_quote: str | None = None
    document_kind: str = "xhtml"
    convert: bool = True
    skip_reason: str | None = None

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
    rules: tuple[object, ...] = ()


@dataclass(frozen=True)
class ConvertRequest:
    config: str
    segmentation: str = "mmseg"
    rules_snapshot: RuleSnapshot = field(default_factory=RuleSnapshot)
    language_tag: str | None = None
    profile_id: str = ""
    book_fingerprint: str = ""
    quotation_mode: str = "keep"
    punctuation_mode: str = "keep"
    pivot_chain: tuple[str, ...] = ()
    detailed_classification: bool = True
    diagnose_mixed: bool = True
    include_rule_trace: bool = False


@dataclass(frozen=True, slots=True)
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
    attribution_method: str | None = None
    comparison_stage: str | None = None
    attribution_confidence: str | None = None
    document_kind: str = "xhtml"
    group_id: str = ""


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    span: SourceSpan | None = None
    line: int | None = None
    column: int | None = None


@dataclass(frozen=True)
class RuleTrace:
    """One selected rule match, with offsets in the input to its named stage."""

    rule_id: str
    action: str
    stage: str
    source: str
    target: str
    start: int
    end: int


@dataclass(frozen=True)
class SkippedRuleTrace:
    """One overlapping candidate skipped by an earlier selected rule."""

    rule_id: str
    winner_id: str
    stage: str
    start: int
    end: int


@dataclass(frozen=True)
class ConvertResult:
    source: str
    target: str
    changes: tuple[TokenChange, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    rule_trace: tuple[RuleTrace, ...] = ()
    after_pre_rules: str = ""
    after_opencc: str = ""
    after_post_rules: str = ""
    zero_width_skips: tuple[tuple[str, int], ...] = ()
    skipped_rule_trace: tuple[SkippedRuleTrace, ...] = ()


@dataclass(frozen=True)
class ConversionPlan:
    """Immutable plan whose allowed spans define the write boundary.

    ``changes`` is the complete set of proposed patches at plan creation.
    Preview decisions create a second plan containing only accepted changes;
    neither operation mutates the original source or the original plan.
    """

    source_sha256: str
    allowed_spans: tuple[SourceSpan, ...] = ()
    changes: tuple[TokenChange, ...] = ()
    config: str = "s2t"
    rules_snapshot: RuleSnapshot = field(default_factory=RuleSnapshot)
    session_id: str = ""
    profile_id: str = ""
    file_id: str = ""
    backend_provenance_hash: str = ""
    targets: tuple[TextTarget, ...] = ()
    source_length: int = 0
    document_kind: str = "xhtml"
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True)
class StagedFile:
    file_id: str
    original: str
    converted: str
    plan: ConversionPlan
    accepted_change_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class VerificationResult:
    file_id: str
    passed: bool
    diagnostics: tuple[Diagnostic, ...] = ()
    checked_change_ids: tuple[str, ...] = ()
