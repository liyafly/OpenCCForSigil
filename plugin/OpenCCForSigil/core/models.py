"""Stable data contracts shared by future pipeline phases."""

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
    """Immutable plan whose allowed spans define the write boundary."""

    source_sha256: str
    allowed_spans: Tuple[SourceSpan, ...] = ()
    changes: Tuple[TokenChange, ...] = ()
    config: str = "s2t"
    rules_snapshot: RuleSnapshot = field(default_factory=RuleSnapshot)


@dataclass(frozen=True)
class StagedFile:
    file_id: str
    original: str
    converted: str
    plan: ConversionPlan


@dataclass(frozen=True)
class VerificationResult:
    file_id: str
    passed: bool
    diagnostics: Tuple[Diagnostic, ...] = ()


class ChineseConverter:
    """Structural protocol placeholder for the Phase 1 converter."""

    def convert(self, text: str, request: ConvertRequest) -> ConvertResult:
        raise NotImplementedError
