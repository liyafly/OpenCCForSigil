import pytest

from sigil.scope import Scope, ScopeSelectionError, TargetSelection, TextFile, resolve_target_selection
from sigil.adapter import SigilBookAdapter


FILES = (
    TextFile("a", "Text/a.xhtml"),
    TextFile("nested-a", "Text/nested/a.xhtml"),
    TextFile("b", "Text/b.xhtml"),
)


def test_all_scope_preserves_text_iter_order():
    selection = resolve_target_selection(FILES, Scope.ALL_XHTML)
    assert selection.file_ids == ("a", "nested-a", "b")
    assert resolve_target_selection((), Scope.ALL_XHTML).empty


def test_selected_scope_uses_manifest_ids_and_rejects_empty():
    selection = resolve_target_selection(FILES, Scope.SELECTED, ("nested-a", "b"))
    assert selection.file_ids == ("nested-a", "b")
    with pytest.raises(ScopeSelectionError):
        resolve_target_selection(FILES, Scope.SELECTED)


def test_single_scope_requires_exactly_one_known_file():
    assert resolve_target_selection(FILES, Scope.SINGLE, ("b",)).file_ids == ("b",)
    with pytest.raises(ScopeSelectionError):
        resolve_target_selection(FILES, Scope.SINGLE, ("a", "b"))
    with pytest.raises(ScopeSelectionError):
        resolve_target_selection(FILES, Scope.SINGLE, ("missing",))


def test_target_selection_rejects_duplicate_ids():
    with pytest.raises(ValueError):
        TargetSelection(Scope.SELECTED, ("a", "a"))


class MetadataBook:
    def __init__(self):
        self.reads = []

    def text_iter(self):
        yield "a", "Text/a.xhtml"
        yield "b", "Text/b.xhtml"

    def selected_iter(self):
        yield "manifest", "b"
        yield "other", "cover.jpg"

    def readfile(self, file_id):
        self.reads.append(file_id)
        return "<p />"


def test_adapter_inventory_and_selection_are_metadata_only():
    book = MetadataBook()
    adapter = SigilBookAdapter(book)
    assert adapter.text_file_inventory()[1].href == "Text/b.xhtml"
    assert tuple(adapter.selected_ids()) == ("b",)
    assert tuple(adapter.text_files_for_targets(TargetSelection(Scope.SINGLE, ("b",)))) == (
        ("b", "Text/b.xhtml"),
    )
    assert book.reads == []


def test_empty_book_browser_selection_never_expands_to_all():
    book = MetadataBook()
    book.selected_iter = lambda: iter(())
    adapter = SigilBookAdapter(book)
    assert tuple(adapter.selected_ids()) == ()
    with pytest.raises(ScopeSelectionError):
        resolve_target_selection(adapter.text_file_inventory(), Scope.SELECTED, ())
