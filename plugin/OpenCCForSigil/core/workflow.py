"""Book-level SCAN → PLAN → PREVIEW → STAGE → VERIFY workflow."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event
from typing import Callable, Iterable, Optional, Tuple

from core.models import ConversionPlan, ConvertRequest
from core.planner import build_conversion_plan
from core.preview import PreviewSession
from core.staging import StagedFile, StagingArea, source_sha256
from core.verifier import verify_staged_file
from document.tokenizer import TokenizedDocument, TokenizerOptions, tokenize_xhtml
from document.xml_processor import tokenize_xml
from transforms.language_tags import with_language_targets
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
    document_kind: str = "xhtml"


@dataclass(frozen=True)
class PlannedDocument:
    source: SourceDocument
    tokenized: TokenizedDocument
    plan: ConversionPlan


def _report_progress(
    progress: Optional[Callable[[str, int, int, str], None]],
    cancelled: Optional[Callable[[], bool]],
    *,
    phase: str,
    index: int,
    total: int,
    href: str,
    cancel_message: str,
) -> None:
    """Report a file boundary, then honor cancellation after event pumping."""

    if progress is not None:
        progress(phase, index, total, href)
    if cancelled is not None and cancelled():
        raise WorkflowCancelled(cancel_message)


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
        snapshot_guard=None,
    ) -> None:
        self.adapter = adapter
        self.backend = backend
        self.request = request
        self.scope = scope
        self.targets = targets
        self.tokenizer_options = tokenizer_options or TokenizerOptions()
        self.session_id = session_id
        self.profile_id = profile_id
        self.snapshot_guard = snapshot_guard
        self._sources: Tuple[SourceDocument, ...] = ()
        self._planned: Tuple[PlannedDocument, ...] = ()
        self.staging = StagingArea()
        self._verification = ()
        self._verified_files = ()

    def scan(
        self,
        *,
        progress: Optional[Callable[[str, int, int, str], None]] = None,
        cancelled: Optional[Callable[[], bool]] = None,
    ) -> Tuple[SourceDocument, ...]:
        target_files = tuple(
            self.adapter.conversion_inventory(self.targets)
            if self.targets is not None
            else ((file_id, href, "xhtml") for file_id, href in self.adapter.text_files(self.scope))
        )
        sources = []
        total = len(target_files)
        if not target_files:
            _report_progress(
                progress,
                cancelled,
                phase="analyzing",
                index=0,
                total=0,
                href="…",
                cancel_message="analysis cancelled",
            )
        for index, (file_id, href, kind) in enumerate(target_files, start=1):
            _report_progress(
                progress,
                cancelled,
                phase="analyzing",
                index=index - 1,
                total=total,
                href=href,
                cancel_message="analysis cancelled",
            )
            source = self.adapter.read(file_id)
            sources.append(SourceDocument(file_id=file_id, href=href, source=source, document_kind=kind))
            _report_progress(
                progress,
                cancelled,
                phase="analyzing",
                index=index,
                total=total,
                href=href,
                cancel_message="analysis cancelled",
            )
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
        if not self._sources:
            _report_progress(
                progress,
                cancelled,
                phase="planning",
                index=0,
                total=0,
                href="…",
                cancel_message="analysis cancelled",
            )
        for index, source_document in enumerate(self._sources, start=1):
            _report_progress(
                progress,
                cancelled,
                phase="planning",
                index=index - 1,
                total=total,
                href=source_document.href,
                cancel_message="analysis cancelled",
            )
            planned.append(self._plan_document(source_document))
            _report_progress(
                progress,
                cancelled,
                phase="planning",
                index=index,
                total=total,
                href=source_document.href,
                cancel_message="analysis cancelled",
            )
        self._planned = tuple(planned)
        return self._planned

    def plan_in_worker(self, backend_factory, *, progress=None, cancelled=None):
        """Read on the caller thread; construct/use/close a backend in its worker.

        Only immutable source/request data and progress tuples cross threads.
        Cancellation is cooperative between targets; a running native call must
        return before shutdown. No Qt or BookContainer API is used by the worker.
        """
        sources = self.scan(progress=progress, cancelled=cancelled)
        if not sources:
            self._planned = ()
            return ()
        stop = Event()
        updates = Queue()

        def check_cancel():
            if stop.is_set():
                raise WorkflowCancelled("analysis cancelled")

        def work():
            backend = backend_factory(self.request.config)
            try:
                results = []
                for index, source in enumerate(sources):
                    check_cancel()
                    updates.put(("planning", index, len(sources), source.href))
                    results.append(self._plan_document(
                        source, backend=backend, check_cancel=check_cancel))
                    check_cancel()
                    updates.put(("planning", index + 1, len(sources), source.href))
                return tuple(results)
            finally:
                backend.close()

        last = ("planning", 0, len(sources), sources[0].href)
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="OpenCC-plan") as pool:
            future = pool.submit(work)
            try:
                while not future.done():
                    try:
                        last = updates.get(timeout=0.025)
                    except Empty:
                        pass
                    if progress:
                        progress(*last)
                    if cancelled and cancelled():
                        stop.set()
                result = future.result()
                if cancelled and cancelled():
                    stop.set()
                check_cancel()
                if progress:
                    progress("planning", len(sources), len(sources), sources[-1].href)
            finally:
                stop.set()
        self._planned = result
        return result

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
        if any(preview.plan != planned.plan for planned, preview in zip(self._planned, sessions)):
            raise WorkflowError("preview plan changed; rescan required")
        finalized = tuple(
            (planned, preview.finalize(require_explicit=require_explicit))
            for planned, preview in zip(self._planned, sessions)
        )
        grouped = {}
        accepted = {change.change_id for _, plan in finalized for change in plan.changes}
        for item in self._planned:
            for change in item.plan.changes:
                if change.group_id:
                    grouped.setdefault(change.group_id, set()).add(change.change_id)
        if any(ids & accepted and not ids <= accepted for ids in grouped.values()):
            raise WorkflowError("grouped language changes must be accepted or skipped together")
        return finalized

    def stage(
        self,
        finalized: Iterable[Tuple[PlannedDocument, ConversionPlan]],
        *,
        progress: Optional[Callable[[str, int, int, str], None]] = None,
        cancelled: Optional[Callable[[], bool]] = None,
    ) -> Tuple[StagedFile, ...]:
        finalized_files = tuple(finalized)
        staged = []
        total = len(finalized_files)
        if not finalized_files:
            _report_progress(
                progress,
                cancelled,
                phase="staging",
                index=0,
                total=0,
                href="…",
                cancel_message="staging cancelled",
            )
        for index, (planned, selected_plan) in enumerate(finalized_files, start=1):
            _report_progress(
                progress,
                cancelled,
                phase="staging",
                index=index - 1,
                total=total,
                href=planned.source.href,
                cancel_message="staging cancelled",
            )
            if selected_plan.changes:
                staged.append(
                    self.staging.stage(
                        planned.source.file_id,
                        planned.source.source,
                        selected_plan,
                    )
                )
            _report_progress(
                progress,
                cancelled,
                phase="staging",
                index=index,
                total=total,
                href=planned.source.href,
                cancel_message="staging cancelled",
            )
        return tuple(staged)

    def verify(
        self,
        staged: Optional[Iterable[StagedFile]] = None,
        *,
        progress: Optional[Callable[[str, int, int, str], None]] = None,
        cancelled: Optional[Callable[[], bool]] = None,
    ):
        files = tuple(staged) if staged is not None else tuple(self.staging.values())
        planned_by_id = {item.source.file_id: item for item in self._planned}
        results = []
        total = len(files)
        if not files:
            _report_progress(
                progress,
                cancelled,
                phase="verifying",
                index=0,
                total=0,
                href="…",
                cancel_message="verification cancelled",
            )
        for index, staged_file in enumerate(files, start=1):
            planned = planned_by_id.get(staged_file.file_id)
            href = planned.source.href if planned is not None else staged_file.file_id
            _report_progress(
                progress,
                cancelled,
                phase="verifying",
                index=index - 1,
                total=total,
                href=href,
                cancel_message="verification cancelled",
            )
            result = verify_staged_file(
                staged_file,
                tokenizer_options=self.tokenizer_options,
                original_document=planned.tokenized if planned is not None else None,
            )
            results.append(result)
            _report_progress(
                progress,
                cancelled,
                phase="verifying",
                index=index,
                total=total,
                href=href,
                cancel_message="verification cancelled",
            )
        self._verification = tuple(results)
        if not all(result.passed for result in self._verification):
            raise WorkflowError("structural verification failed; commit is blocked")
        self._verified_files = files
        return self._verification

    def commit(self, staged: Optional[Iterable[StagedFile]] = None) -> CommitResult:
        files = tuple(staged) if staged is not None else tuple(self.staging.values())
        if not files:
            return CommitResult()
        if not self._verification or not all(result.passed for result in self._verification):
            raise WorkflowError("verify must pass before commit")
        if files != self._verified_files:
            raise WorkflowError("staged files changed after verification; reverify required")
        for staged_file in files:
            current = self.adapter.read(staged_file.file_id)
            if source_sha256(current) != staged_file.plan.source_sha256:
                raise WorkflowError(
                    f"source changed after preview; rescan required: {staged_file.file_id}"
                )
        if self.snapshot_guard is not None:
            self.snapshot_guard()
        try:
            return self.adapter.commit(
                (staged_file.file_id, staged_file.converted) for staged_file in files
            )
        except CommitError as exc:
            raise WorkflowCommitError(exc) from exc

    def _plan_document(self, source_document: SourceDocument, *, backend=None,
                       check_cancel=None) -> PlannedDocument:
        kind = source_document.document_kind
        if kind in {"ncx", "metadata"}:
            tokenized = tokenize_xml(
                source_document.source, document_kind=kind,
                convert_metadata=bool(self.targets and self.targets.include_metadata),
                include_language=bool(self.request.language_tag),
            )
        else:
            tokenized = tokenize_xhtml(source_document.source, self.tokenizer_options)
            if self.request.language_tag:
                tokenized = with_language_targets(tokenized)
        plan = build_conversion_plan(
            file_id=source_document.file_id,
            source=source_document.source,
            document=tokenized,
            backend=backend if backend is not None else self.backend,
            check_cancel=check_cancel,
            request=self.request,
            session_id=self.session_id,
            profile_id=self.profile_id,
            document_kind=kind,
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
