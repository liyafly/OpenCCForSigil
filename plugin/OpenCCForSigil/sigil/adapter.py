"""Narrow Sigil BookContainer adapter.

Only this adapter's commit method is allowed to call `bk.writefile()` in the
finished implementation. Phase 0 never calls it.
"""

from typing import Any, Iterable, Protocol, Tuple


class BookContainer(Protocol):
    def readfile(self, file_id: str) -> str:
        ...

    def writefile(self, file_id: str, data: str) -> None:
        ...


class SigilBookAdapter:
    """Expose read and final commit operations without leaking `bk` inward."""

    def __init__(self, bk: Any) -> None:
        self._bk = bk

    def read(self, file_id: str) -> str:
        return self._bk.readfile(file_id)

    def commit(self, staged_files: Iterable[Tuple[str, str]]) -> None:
        for file_id, data in staged_files:
            self._bk.writefile(file_id, data)
