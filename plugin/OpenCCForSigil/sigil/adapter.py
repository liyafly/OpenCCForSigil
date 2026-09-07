"""Narrow Sigil BookContainer adapter.

Only this adapter's commit method is allowed to call `bk.writefile()`.
"""

from typing import Any, Iterable, Iterator, Protocol, Tuple

from sigil.scope import Scope, TargetSelection, TextFile


class BookContainer(Protocol):
    def readfile(self, file_id: str) -> str:
        ...

    def writefile(self, file_id: str, data: str) -> None:
        ...

    def text_iter(self) -> Iterable[Tuple[str, str]]:
        ...


class SigilBookAdapter:
    """Expose read and final commit operations without leaking `bk` inward."""

    def __init__(self, bk: Any) -> None:
        self._bk = bk

    def read(self, file_id: str) -> str:
        return self._bk.readfile(file_id)

    def text_files(self, scope: Scope = Scope.ALL_XHTML) -> Iterator[Tuple[str, str]]:
        """Yield manifest id and href according to the selected scope."""

        if scope is Scope.ALL_XHTML:
            yield from self._bk.text_iter()
            return
        if scope is Scope.SPINE:
            xhtml_ids = {file_id for file_id, _href in self._bk.text_iter()}
            for item in self._bk.spine_iter():
                file_id, _linear, href = item
                if file_id in xhtml_ids:
                    yield file_id, href
            return
        if scope is Scope.SELECTED:
            xhtml_ids = {file_id: href for file_id, href in self._bk.text_iter()}
            for item_type, file_id in self._bk.selected_iter():
                if item_type == "manifest" and file_id in xhtml_ids:
                    yield file_id, xhtml_ids[file_id]
            return
        raise ValueError(f"unsupported scope: {scope}")

    def text_file_inventory(self) -> Tuple[TextFile, ...]:
        """Return XHTML metadata in Sigil order without reading file bodies."""

        return tuple(TextFile(file_id, href) for file_id, href in self._bk.text_iter())

    def selected_ids(self) -> Iterator[str]:
        """Return only manifest ids selected in the Book Browser."""

        selected_iter = getattr(self._bk, "selected_iter", None)
        if not callable(selected_iter):
            return
        for item_type, file_id in selected_iter():
            if item_type == "manifest":
                yield file_id

    def text_files_for_targets(
        self, selection: TargetSelection
    ) -> Iterator[Tuple[str, str]]:
        """Yield only the frozen target ids, preserving inventory order."""

        by_id = {item.file_id: item for item in self.text_file_inventory()}
        missing = [file_id for file_id in selection.file_ids if file_id not in by_id]
        if missing:
            raise ValueError("target XHTML disappeared: " + ", ".join(missing))
        for file_id in selection.file_ids:
            item = by_id[file_id]
            yield item.file_id, item.href

    def commit(self, staged_files: Iterable[Tuple[str, str]]) -> None:
        for file_id, data in staged_files:
            self._bk.writefile(file_id, data)
