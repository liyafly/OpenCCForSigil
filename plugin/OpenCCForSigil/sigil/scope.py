"""Book selection scopes and immutable target selections."""

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping, Tuple


class Scope(str, Enum):
    SINGLE = "single"
    ALL_XHTML = "all_xhtml"
    SPINE = "spine"
    SELECTED = "selected"


@dataclass(frozen=True)
class TextFile:
    """Metadata for one XHTML resource; constructing this never reads content."""

    file_id: str
    href: str


@dataclass(frozen=True)
class TargetSelection:
    """Frozen, ordered manifest ids used by one conversion invocation."""

    scope: Scope
    file_ids: Tuple[str, ...]

    def __post_init__(self) -> None:
        ids = tuple(self.file_ids)
        if len(ids) != len(set(ids)):
            raise ValueError("target selection contains duplicate file ids")
        if any(not isinstance(file_id, str) or not file_id for file_id in ids):
            raise ValueError("target selection contains an invalid file id")

    @property
    def empty(self) -> bool:
        return not self.file_ids


class ScopeSelectionError(ValueError):
    """Raised when a requested target is not an available XHTML resource."""


def resolve_target_selection(
    files: Iterable[TextFile],
    scope: Scope,
    selected_ids: Iterable[str] = (),
) -> TargetSelection:
    """Resolve a UI choice against metadata without touching ``readfile``.

    ``files`` is expected in Sigil's text_iter order. Selection ids are always
    resolved by manifest id, never by basename, so same-named files remain
    distinguishable.
    """

    inventory = tuple(files)
    by_id: Mapping[str, TextFile] = {item.file_id: item for item in inventory}
    requested = tuple(selected_ids)
    if len(requested) != len(set(requested)):
        raise ScopeSelectionError("target selection contains duplicate file ids")
    unknown = tuple(file_id for file_id in requested if file_id not in by_id)
    if unknown:
        raise ScopeSelectionError("unknown XHTML target(s): " + ", ".join(unknown))
    if scope is Scope.ALL_XHTML:
        ids = tuple(item.file_id for item in inventory)
    elif scope in {Scope.SINGLE, Scope.SELECTED}:
        ids = requested
        if scope is Scope.SINGLE and len(ids) != 1:
            raise ScopeSelectionError("single-file scope requires exactly one XHTML target")
        if scope is Scope.SELECTED and not ids:
            raise ScopeSelectionError("at least one XHTML target is required")
    elif scope is Scope.SPINE:
        ids = requested
    else:  # pragma: no cover - Enum exhaustiveness guard
        raise ScopeSelectionError(f"unsupported scope: {scope}")
    return TargetSelection(scope=scope, file_ids=ids)
