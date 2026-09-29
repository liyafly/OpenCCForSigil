import pytest

from sigil.scope import (
    Scope,
    ScopeSelectionError,
    TargetSelection,
    TextFile,
    resolve_target_selection,
)
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


def test_scope_enum_contains_only_supported_modes():
    assert {scope.value for scope in Scope} == {"all_xhtml", "spine", "selected"}


def test_all_scope_preserves_text_iter_order():
    selection = resolve_target_selection(FILES, Scope.ALL_XHTML)
    assert selection.file_ids == ("a", "nested-a", "b")
    assert resolve_target_selection((), Scope.ALL_XHTML).empty


def test_selected_scope_uses_manifest_ids_and_rejects_empty():
    selection = resolve_target_selection(FILES, Scope.SELECTED, ("nested-a", "b"))
    assert selection.file_ids == ("nested-a", "b")
    with pytest.raises(ScopeSelectionError):
        resolve_target_selection(FILES, Scope.SELECTED)
    with pytest.raises(ScopeSelectionError):
        resolve_target_selection(FILES, Scope.SELECTED, ("missing",))


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
    assert tuple(adapter.text_files_for_targets(TargetSelection(Scope.SELECTED, ("b",)))) == (
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
    inventory = (
        TextFile("one", "Text/one.xhtml"),
        TextFile("two", "Text/two.xhtml"),
    )
    dialog = _ScopeDialog(
        make_with_table(),
        inventory,
        ("one",),
        "en",
        Translator("en"),
        embedded=True,
    )

    assert dialog.selected_radio.isChecked()
    assert (
        sum(
            radio.isVisible()
            for radio in (
                dialog.selected_radio,
                dialog.spine_radio,
                dialog.all_radio,
            )
        )
        == 3
    )
    assert dialog.list_widget.item(0).checkState() == dialog._qt.Qt.Checked
    assert dialog.selected_ids() == ("one",)

    dialog.list_widget.setCurrentRow(1)
    assert dialog.selected_ids() == ("one",)
    dialog.list_widget.item(1).setCheckState(dialog._qt.Qt.Checked)
    assert dialog.selected_ids() == ("one", "two")
    dialog._accept(close=False)

    assert dialog.scope is Scope.SELECTED
    assert dialog.selection.file_ids == ("one", "two")


def test_single_initial_selection_accepts_as_selected_scope():
    inventory = (
        TextFile("one", "Text/one.xhtml"),
        TextFile("two", "Text/two.xhtml"),
    )
    dialog = _ScopeDialog(
        make_with_table(),
        inventory,
        ("one",),
        "en",
        Translator("en"),
        embedded=True,
    )

    dialog._accept(close=False)

    assert dialog.selection.scope is Scope.SELECTED
    assert dialog.selection.file_ids == ("one",)


def test_fixed_scope_modes_make_list_read_only():
    dialog = _ScopeDialog(
        make_with_table(),
        FILES,
        ("a",),
        "en",
        Translator("en"),
        spine_ids=("a", "b"),
        embedded=True,
    )
    checkable = dialog._qt.Qt.ItemIsUserCheckable

    for radio, checked_ids in (
        (dialog.spine_radio, {"a", "b"}),
        (dialog.all_radio, {"a", "nested-a", "b"}),
    ):
        radio.setChecked(True)
        for index, file_id in enumerate(("a", "nested-a", "b")):
            item = dialog.list_widget.item(index)
            assert item.flags() & checkable == 0
            original = item.checkState()
            attempt = (
                dialog._qt.Qt.Unchecked
                if original == dialog._qt.Qt.Checked
                else dialog._qt.Qt.Checked
            )
            item.setCheckState(attempt)
            assert item.checkState() == original
            assert (original == dialog._qt.Qt.Checked) is (file_id in checked_ids)

    dialog.selected_radio.setChecked(True)
    assert all(
        dialog.list_widget.item(index).flags() & checkable
        for index in range(dialog.list_widget.count())
    )


def test_scope_filter_enter_focuses_first_visible_row_without_accepting():
    dialog = _ScopeDialog(make_with_table(), FILES, (), "en", Translator("en"), embedded=True)
    dialog.filter_edit.setText("nested")
    dialog.filter_edit.textChanged.emit("nested")

    dialog.filter_edit.returnPressed.emit()

    assert dialog.list_widget.currentRow() == 1
    assert dialog.accepted is False
    assert not hasattr(dialog, "analyze_button")
    assert all(
        button.autoDefault() is False
        for button in (
            dialog.select_visible,
            dialog.clear_visible,
        )
    )


def test_filter_enter_guard_consumes_key_and_focuses_first_row():
    dialog = _ScopeDialog(make_with_table(), FILES, (), "en", Translator("en"), embedded=True)
    dialog.filter_edit.setText("nested")
    dialog.filter_edit.textChanged.emit("nested")

    assert dialog._filter_enter_pressed() is True
    assert dialog.list_widget.currentRow() == 1
    assert dialog.accepted is False


def test_scope_labels_are_buddied_and_filter_list_have_accessible_names():
    dialog = _ScopeDialog(
        make_with_table(),
        FILES,
        (),
        "en",
        Translator("en"),
        embedded=True,
    )

    assert dialog.language_label.buddy() is dialog.language_combo
    assert dialog.filter_edit.accessibleName()
    assert dialog.list_widget.accessibleName()


def test_scope_language_change_retranslates_guide_navigation_and_recovery_notice():
    translator = Translator("zh-Hans")
    inventory = (TextFile("chapter", "Text/chapter.xhtml"), TextFile("nav", "Text/nav.xhtml"))
    dialog = _ScopeDialog(
        make_with_table(),
        inventory,
        (),
        "zh-Hans",
        translator,
        nav_id="nav",
        recovery_notices=(("preferences_corrupt", "preferences.json"),),
        embedded=True,
    )
    assert "导航" in dialog.list_widget.item(1).text()
    assert "损坏" in dialog.recovery_notice_label.text()

    dialog.language_combo.setCurrentIndex(dialog.language_combo.findData("en"))

    english = Translator("en")
    assert dialog.guide_label.text() == english.text("scope.selection_guide")
    assert dialog.list_widget.item(1).text() == (
        "Text/nav.xhtml " + english.text("scope.navigation_suffix")
    )
    assert dialog.recovery_notice_label.text() == english.text(
        "recovery.preferences_corrupt", value="preferences.json"
    )


def test_scope_list_middle_elides_and_keeps_complete_path_in_tooltip():
    qt = make_with_table()
    inventory = (TextFile("nav", "Text/very/long/navigation/path/nav.xhtml"),)
    dialog = _ScopeDialog(qt, inventory, (), "en", Translator("en"), nav_id="nav", embedded=True)

    assert ("setTextElideMode", (qt.Qt.ElideMiddle,)) in dialog.list_widget.calls
    assert dialog.list_widget.item(0).toolTip() == inventory[0].href
    assert (
        dialog.list_widget.item(0).text().endswith(Translator("en").text("scope.navigation_suffix"))
    )


def test_scope_notice_banners_use_information_icons_and_palette_surface():
    qt = make_with_table()
    dialog = _ScopeDialog(
        qt,
        (TextFile("chapter", "Text/chapter.xhtml"),),
        (),
        "en",
        Translator("en"),
        recovery_notices=(("preferences_corrupt", "preferences.json"),),
        embedded=True,
    )

    banner = dialog.recovery_notice_banner
    assert "#f5f5f5" in banner.styleSheet()
    assert banner.palette().requested_roles == [qt.QtGui.QPalette.AlternateBase]
    assert banner.style().requested_icon == qt.QStyle.SP_MessageBoxInformation


def test_scope_dialog_has_no_checkpoint_banner_but_keeps_recovery_notice():
    dialog = _ScopeDialog(
        make_with_table(),
        (TextFile("chapter", "Text/chapter.xhtml"),),
        (),
        "en",
        Translator("en"),
        recovery_notices=(("preferences_corrupt", "preferences.json"),),
        embedded=True,
    )

    assert not hasattr(dialog, "checkpoint_banner")
    assert dialog.recovery_notice_banner is not None


def test_selected_file_count_remains_visible_when_filter_hides_it():
    dialog = _ScopeDialog(
        make_with_table(),
        FILES,
        ("a",),
        "en",
        Translator("en"),
        embedded=True,
    )
    dialog.filter_edit.setText("nested/a.xhtml")
    dialog.filter_edit.textChanged.emit("nested/a.xhtml")

    assert dialog.count_label.text() == "Selected 1 / 3 XHTML files (visible after filter: 1)"
    assert dialog.selected_ids() == ("a",)
    assert dialog.list_widget.item(0).isHidden()
