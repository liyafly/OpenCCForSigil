"""In-memory staging boundary; no Sigil writes occur here."""

from hashlib import sha256
from typing import Dict, Iterable, Sequence

from core.models import ConversionPlan, StagedFile, TokenChange


class StagingError(ValueError):
    """Raised when a frozen plan cannot be applied safely."""


class StagingArea:
    """Hold converted documents before verification and adapter commit."""

    def __init__(self) -> None:
        self._files: Dict[str, StagedFile] = {}

    def add(self, staged_file: StagedFile) -> None:
        self._files[staged_file.file_id] = staged_file

    def stage(self, file_id: str, source: str, plan: ConversionPlan) -> StagedFile:
        if plan.file_id and plan.file_id != file_id:
            raise StagingError("plan file_id does not match staged file")
        if plan.source_sha256 != source_sha256(source):
            raise StagingError("source SHA256 does not match the frozen plan")
        converted = apply_changes(source, plan.changes)
        staged_file = StagedFile(
            file_id=file_id,
            original=source,
            converted=converted,
            plan=plan,
            accepted_change_ids=tuple(change.change_id for change in plan.changes),
        )
        self.add(staged_file)
        return staged_file

    def values(self) -> Iterable[StagedFile]:
        return self._files.values()

    def __len__(self) -> int:
        return len(self._files)


def apply_changes(source: str, changes: Sequence[TokenChange]) -> str:
    """Apply frozen non-overlapping source patches from right to left."""

    _validate_source_changes(source, changes)
    result = source
    for change in sorted(changes, key=lambda item: (item.span.start, item.span.end), reverse=True):
        result = result[: change.span.start] + change.target + result[change.span.end :]
    return result


def source_sha256(source: str) -> str:
    return sha256(source.encode("utf-8")).hexdigest()


def _validate_source_changes(source: str, changes: Sequence[TokenChange]) -> None:
    previous_start = -1
    previous_end = -1
    for change in sorted(changes, key=lambda item: (item.span.start, item.span.end)):
        span = change.span
        if span.end > len(source):
            raise StagingError(f"change span exceeds source length: {span}")
        if source[span.start : span.end] != change.source:
            raise StagingError(
                f"source changed at planned span {span}: "
                f"expected {change.source!r}, found {source[span.start:span.end]!r}"
            )
        if previous_end >= 0 and (
            span.start < previous_end
            or (span.start == previous_start == span.end == previous_end)
        ):
            raise StagingError(f"overlapping change spans: {span}")
        previous_start = span.start
        previous_end = span.end
