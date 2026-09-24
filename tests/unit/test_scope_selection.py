from types import SimpleNamespace

import pytest

from sigil.scope import Scope, ScopeSelectionError, TargetSelection, TextFile, resolve_target_selection
from sigil.adapter import SigilBookAdapter
from tests.support.fake_qt import make_with_table
from ui.i18n import Translator
from ui.preview_window import (
    _ScopeDialog,
    _ordered_scope_inventory,
    _selected_xhtml_ids_and_ignored,
    _spine_ids,
)


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


def test_missing_selection_api_and_non_xhtml_selection_are_safe():
    inventory = (TextFile("chapter", "Text/chapter.xhtml"),)

    class NoSelectionApi:
        pass

    assert _selected_xhtml_ids_and_ignored(NoSelectionApi(), inventory) == ((), 0)

    class MixedSelection:
        def selected_ids(self):
            return iter(("chapter", "cover"))

    assert _selected_xhtml_ids_and_ignored(MixedSelection(), inventory) == (("chapter",), 1)


def test_spine_ids_are_read_from_adapter_metadata_without_content_reads():
    calls = []

    class SpineAdapter:
        def text_files(self, scope):
            calls.append(scope)
            assert scope is Scope.SPINE
            return iter((("spine-a", "Text/a.xhtml"), ("spine-b", "Text/b.xhtml")))

    adapter = SpineAdapter()
    assert _spine_ids(adapter) == ("spine-a", "spine-b")
    assert calls == [Scope.SPINE]
    assert resolve_target_selection(FILES, Scope.SPINE, ("a", "b")).file_ids == ("a", "b")


def test_scope_inventory_uses_spine_order_then_path_order():
    inventory = (
        TextFile("loose-z", "Text/z.xhtml"),
        TextFile("spine-b", "Text/b.xhtml"),
        TextFile("loose-a", "Text/a.xhtml"),
        TextFile("spine-a", "Text/a-spine.xhtml"),
    )

    ordered = _ordered_scope_inventory(inventory, ("spine-b", "spine-a"))

    assert tuple(item.file_id for item in ordered) == (
        "spine-b", "spine-a", "loose-a", "loose-z")


def test_single_scope_uses_one_row_selection_and_manual_selection_is_independent():
    class Radio:
        def __init__(self, checked):
            self.checked = checked

        def isChecked(self):
            return self.checked

    class Item:
        def __init__(self, identifier):
            self.identifier = identifier

        def data(self, _role):
            return self.identifier

    class List:
        def __init__(self):
            self.row = 1

        def currentRow(self):
            return self.row

        def item(self, row):
            return (Item("one"), Item("two"))[row]

        def count(self):
            return 2

    dialog = object.__new__(_ScopeDialog)
    dialog.single_radio = Radio(True)
    dialog.selected_radio = Radio(False)
    dialog.spine_radio = Radio(False)
    dialog.all_radio = Radio(False)
    dialog.list_widget = List()
    dialog._inventory = (TextFile("one", "Text/one.xhtml"),
                        TextFile("two", "Text/two.xhtml"))
    dialog._qt = SimpleNamespace(Qt=SimpleNamespace(UserRole=32))
    dialog._manual_selection_ids = {"one"}
    dialog._single_selected_id = "one"

    assert dialog.selected_ids() == ("two",)
    dialog.single_radio.checked = False
    dialog.selected_radio.checked = True
    assert dialog.selected_ids() == ("one",)


def test_scope_filter_enter_focuses_first_visible_row_without_accepting():
    dialog = _ScopeDialog(
        make_with_table(), FILES, (), "en", Translator("en"))
    dialog.filter_edit.setText("nested")
    dialog.filter_edit.textChanged.emit("nested")

    dialog.filter_edit.returnPressed.emit()

    assert dialog.list_widget.currentRow() == 1
    assert dialog.accepted is False
    assert dialog.analyze_button.isDefault()
    assert dialog.analyze_button.autoDefault() is False
    assert all(
        button.autoDefault() is False
        for button in (
            dialog.select_visible,
            dialog.clear_visible,
            dialog.cancel_button,
            dialog.analyze_button,
        )
    )


def test_scope_language_change_retranslates_guide_navigation_and_recovery_notice():
    translator = Translator("zh-Hans")
    inventory = (TextFile("chapter", "Text/chapter.xhtml"),
                 TextFile("nav", "Text/nav.xhtml"))
    dialog = _ScopeDialog(
        make_with_table(),
        inventory,
        (),
        "zh-Hans",
        translator,
        nav_id="nav",
        recovery_notices=(("preferences_corrupt", "preferences.json"),),
    )
    assert "导航" in dialog.list_widget.item(1).text()
    assert "损坏" in dialog.recovery_notice_label.text()

    dialog.language_combo.setCurrentIndex(dialog.language_combo.findData("en"))

    english = Translator("en")
    assert dialog.guide_label.text() == english.text("scope.selection_guide")
    assert dialog.list_widget.item(1).text() == (
        "Text/nav.xhtml " + english.text("scope.navigation_suffix"))
    assert dialog.recovery_notice_label.text() == english.text(
        "recovery.preferences_corrupt", value="preferences.json")
