"""Book-level SCAN → PLAN → PREVIEW → STAGE → VERIFY workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Tuple

from core.models import ConversionPlan, ConvertRequest
from core.planner import build_conversion_plan
from core.preview import PreviewSession
from core.staging import StagedFile, StagingArea, source_sha256
from core.verifier import verify_staged_file
from document.tokenizer import TokenizedDocument, TokenizerOptions, tokenize_xhtml
from opencc_backend.backend import OpenCCBackend
from sigil.adapter import CommitError, CommitResult, SigilBookAdapter
from sigil.scope import Scope, TargetSelection


class WorkflowError(RuntimeError):
    """Raised when a workflow phase cannot safely continue."""


class WorkflowCancelled(WorkflowError):
    """Raised at a safe file boundary when the user cancels analysis."""


class WorkflowCommitError(WorkflowError):
    """A commit failed after the adapter handed some files to Sigil."""

    def __init__(self, error: CommitError) -> None:
        self.failed_file_id = error.file_id
        self.committed_file_ids = error.committed_file_ids
        self.cause = error.cause
        super().__init__(str(error))


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
        targets: Optional[TargetSelection] = None,
        tokenizer_options: Optional[TokenizerOptions] = None,
        session_id: str = "",
        profile_id: str = "",
    ) -> None:
        self.adapter = adapter
        self.backend = backend
        self.request = request
        self.scope = scope
        self.targets = targets
        self.tokenizer_options = tokenizer_options or TokenizerOptions()
        self.session_id = session_id
        self.profile_id = profile_id
        self._sources: Tuple[SourceDocument, ...] = ()
        self._planned: Tuple[PlannedDocument, ...] = ()
        self.staging = StagingArea()
        self._verification = ()

    def scan(
        self,
        *,
        progress: Optional[Callable[[str, int, int, str], None]] = None,
        cancelled: Optional[Callable[[], bool]] = None,
    ) -> Tuple[SourceDocument, ...]:
        target_files = tuple(
            self.adapter.text_files_for_targets(self.targets)
            if self.targets is not None
            else self.adapter.text_files(self.scope)
        )
        sources = []
        total = len(target_files)
        for index, (file_id, href) in enumerate(target_files, start=1):
            if cancelled is not None and cancelled():
                raise WorkflowCancelled("analysis cancelled")
            source = self.adapter.read(file_id)
            sources.append(SourceDocument(file_id=file_id, href=href, source=source))
            # A progress callback pumps Qt events. Report the completed read,
            # then honor cancellation before starting the next file.
            if progress is not None:
                progress("analyzing", index, total, href)
            if cancelled is not None and cancelled():
                raise WorkflowCancelled("analysis cancelled")
        self._sources = tuple(sources)
        return self._sources

    def plan(
        self,
        *,
        progress: Optional[Callable[[str, int, int, str], None]] = None,
        cancelled: Optional[Callable[[], bool]] = None,
    ) -> Tuple[PlannedDocument, ...]:
        if not self._sources:
            self.scan(progress=progress, cancelled=cancelled)
        planned = []
        total = len(self._sources)
        for index, source_document in enumerate(self._sources, start=1):
            if cancelled is not None and cancelled():
                raise WorkflowCancelled("analysis cancelled")
            planned.append(self._plan_document(source_document))
            if progress is not None:
                progress("planning", index, total, source_document.href)
            if cancelled is not None and cancelled():
                raise WorkflowCancelled("analysis cancelled")
        self._planned = tuple(planned)
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
        *,
        progress: Optional[Callable[[str, int, int, str], None]] = None,
    ) -> Tuple[StagedFile, ...]:
        finalized_files = tuple(finalized)
        staged = []
        total = len(finalized_files)
        for index, (planned, selected_plan) in enumerate(finalized_files, start=1):
            if selected_plan.changes:
                staged.append(
                    self.staging.stage(
                        planned.source.file_id,
                        planned.source.source,
                        selected_plan,
                    )
                )
            if progress is not None:
                progress("staging", index, total, planned.source.href)
        return tuple(staged)

    def verify(
        self,
        staged: Optional[Iterable[StagedFile]] = None,
        *,
        progress: Optional[Callable[[str, int, int, str], None]] = None,
    ):
        files = tuple(staged) if staged is not None else tuple(self.staging.values())
        planned_by_id = {item.source.file_id: item for item in self._planned}
        results = []
        total = len(files)
        for index, staged_file in enumerate(files, start=1):
            planned = planned_by_id.get(staged_file.file_id)
            result = verify_staged_file(
                staged_file,
                tokenizer_options=self.tokenizer_options,
                original_document=planned.tokenized if planned is not None else None,
            )
            results.append(result)
            if progress is not None:
                href = planned.source.href if planned is not None else staged_file.file_id
                progress("verifying", index, total, href)
        self._verification = tuple(results)
        if not all(result.passed for result in self._verification):
            raise WorkflowError("structural verification failed; commit is blocked")
        return self._verification

    def commit(self, staged: Optional[Iterable[StagedFile]] = None) -> CommitResult:
        files = tuple(staged) if staged is not None else tuple(self.staging.values())
        if not files:
            return CommitResult()
        if not self._verification or not all(result.passed for result in self._verification):
            raise WorkflowError("verify must pass before commit")
        for staged_file in files:
            current = self.adapter.read(staged_file.file_id)
            if source_sha256(current) != staged_file.plan.source_sha256:
                raise WorkflowError(
                    f"source changed after preview; rescan required: {staged_file.file_id}"
                )
        try:
            return self.adapter.commit(
                (staged_file.file_id, staged_file.converted) for staged_file in files
            )
        except CommitError as exc:
            raise WorkflowCommitError(exc) from exc

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
    "WorkflowCancelled",
    "WorkflowCommitError",
]
