"""In-memory staging boundary; no Sigil writes occur here."""

from typing import Dict, Iterable

from core.models import StagedFile


class StagingArea:
    """Hold converted documents before verification and adapter commit."""

    def __init__(self) -> None:
        self._files: Dict[str, StagedFile] = {}

    def add(self, staged_file: StagedFile) -> None:
        self._files[staged_file.file_id] = staged_file

    def values(self) -> Iterable[StagedFile]:
        return self._files.values()

    def __len__(self) -> int:
        return len(self._files)
