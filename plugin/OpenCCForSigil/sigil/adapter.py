"""Narrow Sigil BookContainer adapter.

Only this adapter's commit method is allowed to call `bk.writefile()`.
"""

from dataclasses import dataclass
from typing import Any, Iterable, Iterator, Protocol, Tuple

from sigil.scope import Scope, TargetSelection, TextFile


METADATA_ID = "urn:opencc-for-sigil:metadata"


class BookContainer(Protocol):
    def readfile(self, file_id: str) -> str:
        ...

    def writefile(self, file_id: str, data: str) -> None:
        ...

    def text_iter(self) -> Iterable[Tuple[str, str]]:
        ...


@dataclass(frozen=True)
class CommitResult:
    """Files successfully handed to Sigil's write boundary."""

    committed_file_ids: Tuple[str, ...] = ()


class CommitError(RuntimeError):
    """A write failed after zero or more files had already been committed."""

    def __init__(
        self,
        file_id: str,
        committed_file_ids: Iterable[str],
        cause: BaseException,
    ) -> None:
        self.file_id = file_id
        self.committed_file_ids = tuple(committed_file_ids)
        self.cause = cause
        super().__init__(f"writefile failed for {file_id}: {cause}")


class SigilBookAdapter:
    """Expose read and final commit operations without leaking `bk` inward."""

    def __init__(self, bk: Any) -> None:
        self._bk = bk

    def read(self, file_id: str) -> str:
        if file_id == METADATA_ID:
            return self._bk.getmetadataxml()
        return self._bk.readfile(file_id)

    def metadata_supported(self) -> bool:
        return all(callable(getattr(self._bk, name, None))
                   for name in ("getmetadataxml", "setmetadataxml"))

    def nav_id(self) -> str | None:
        method = getattr(self._bk, "getnavid", None)
        return method() if callable(method) else None

    def conversion_inventory(self, selection: TargetSelection):
        """Freeze explicitly selected resources, without reading their bodies."""
        nav_id = self.nav_id()
        for file_id, href in self.text_files_for_targets(selection):
            if file_id == nav_id and not selection.include_nav:
                continue
            yield file_id, href, "nav" if file_id == nav_id else "xhtml"
        if selection.include_ncx:
            manifest = getattr(self._bk, "manifest_iter", None)
            if not callable(manifest):
                raise ValueError("host does not expose NCX resource inventory")
            for file_id, href, mime in manifest():
                if mime == "application/x-dtbncx+xml":
                    yield file_id, href, "ncx"
        if selection.include_metadata or selection.update_language:
            if not self.metadata_supported():
                raise ValueError("host does not expose metadata read/write APIs")
            manifest = getattr(self._bk, "manifest_iter", None)
            if callable(manifest) and any(item[0] == METADATA_ID for item in manifest()):
                raise ValueError("manifest ID conflicts with the metadata transaction ID")
            yield METADATA_ID, "OPF metadata", "metadata"

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

    def commit(self, staged_files: Iterable[Tuple[str, str]]) -> CommitResult:
        committed: list[str] = []
        for file_id, data in staged_files:
            try:
                if file_id == METADATA_ID:
                    self._bk.setmetadataxml(data)
                else:
                    self._bk.writefile(file_id, data)
            except Exception as exc:
                raise CommitError(file_id, committed, exc) from exc
            committed.append(file_id)
        return CommitResult(tuple(committed))


__all__ = ["BookContainer", "CommitError", "CommitResult", "SigilBookAdapter"]
