"""Book-level SCAN → PLAN → PREVIEW → STAGE → VERIFY workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

from core.models import ConversionPlan, ConvertRequest
from core.planner import build_conversion_plan
from core.preview import PreviewSession
from core.staging import StagedFile, StagingArea, source_sha256
from core.verifier import verify_staging
from document.tokenizer import TokenizedDocument, TokenizerOptions, tokenize_xhtml
from opencc_backend.backend import OpenCCBackend
from sigil.adapter import SigilBookAdapter
from sigil.scope import Scope


class WorkflowError(RuntimeError):
    """Raised when a workflow phase cannot safely continue."""


@dataclass(frozen=True)
class SourceDocument:
    file_id: str
    href: str
    source: str


@dataclass(frozen=True)
class PlannedDocument:
    source: SourceDocument
    tokenized: TokenizedDocument
    plan: ConversionPlan


class ConversionWorkflow:
    """Coordinate pure core phases around a narrow Sigil adapter."""

    def __init__(
        self,
        adapter: SigilBookAdapter,
        backend: OpenCCBackend,
        request: ConvertRequest,
        *,
        scope: Scope = Scope.ALL_XHTML,
        tokenizer_options: Optional[TokenizerOptions] = None,
        session_id: str = "",
        profile_id: str = "",
    ) -> None:
        self.adapter = adapter
        self.backend = backend
        self.request = request
        self.scope = scope
        self.tokenizer_options = tokenizer_options or TokenizerOptions()
        self.session_id = session_id
        self.profile_id = profile_id
        self._sources: Tuple[SourceDocument, ...] = ()
        self._planned: Tuple[PlannedDocument, ...] = ()
        self.staging = StagingArea()
        self._verification = ()

    def scan(self) -> Tuple[SourceDocument, ...]:
        self._sources = tuple(
            SourceDocument(file_id=file_id, href=href, source=self.adapter.read(file_id))
            for file_id, href in self.adapter.text_files(self.scope)
        )
        return self._sources

    def plan(self) -> Tuple[PlannedDocument, ...]:
        if not self._sources:
            self.scan()
        self._planned = tuple(
            self._plan_document(source_document) for source_document in self._sources
        )
        return self._planned

    def preview(self) -> Tuple[PreviewSession, ...]:
        if not self._planned:
            self.plan()
        return tuple(PreviewSession(item.plan) for item in self._planned)

    def finalize(
        self,
        previews: Iterable[PreviewSession],
        *,
        require_explicit: bool = True,
    ) -> Tuple[Tuple[PlannedDocument, ConversionPlan], ...]:
        sessions = tuple(previews)
        if len(sessions) != len(self._planned):
            raise WorkflowError("preview session count does not match planned documents")
        return tuple(
            (planned, preview.finalize(require_explicit=require_explicit))
            for planned, preview in zip(self._planned, sessions)
        )

    def stage(
        self,
        finalized: Iterable[Tuple[PlannedDocument, ConversionPlan]],
    ) -> Tuple[StagedFile, ...]:
        staged = []
        for planned, selected_plan in finalized:
            staged.append(
                self.staging.stage(
                    planned.source.file_id,
                    planned.source.source,
                    selected_plan,
                )
            )
        return tuple(staged)

    def verify(self, staged: Optional[Iterable[StagedFile]] = None):
        files = tuple(staged) if staged is not None else tuple(self.staging.values())
        self._verification = verify_staging(files, tokenizer_options=self.tokenizer_options)
        if not all(result.passed for result in self._verification):
            raise WorkflowError("structural verification failed; commit is blocked")
        return self._verification

    def commit(self, staged: Optional[Iterable[StagedFile]] = None) -> None:
        files = tuple(staged) if staged is not None else tuple(self.staging.values())
        if not files:
            return
        if not self._verification or not all(result.passed for result in self._verification):
            raise WorkflowError("verify must pass before commit")
        for staged_file in files:
            current = self.adapter.read(staged_file.file_id)
            if source_sha256(current) != staged_file.plan.source_sha256:
                raise WorkflowError(
                    f"source changed after preview; rescan required: {staged_file.file_id}"
                )
        self.adapter.commit(
            (staged_file.file_id, staged_file.converted) for staged_file in files
        )

    def _plan_document(self, source_document: SourceDocument) -> PlannedDocument:
        tokenized = tokenize_xhtml(source_document.source, self.tokenizer_options)
        plan = build_conversion_plan(
            file_id=source_document.file_id,
            source=source_document.source,
            document=tokenized,
            backend=self.backend,
            request=self.request,
            session_id=self.session_id,
            profile_id=self.profile_id,
        )
        return PlannedDocument(source_document, tokenized, plan)


__all__ = [
    "ConversionWorkflow",
    "PlannedDocument",
    "SourceDocument",
    "WorkflowError",
]
