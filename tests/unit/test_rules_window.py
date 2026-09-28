from types import SimpleNamespace
import pytest
from tests.support import fake_qt
from tests.support.fake_qt import make_with_table

from rules.models import Rule
from rules.models import RuleSnapshot
from rules.importers import import_rules
from rules.exporters import export_rules
from rules.store import RuleSet, RuleStore
from rules.conflicts import find_conflicts
from opencc_backend.configs import comparison_configs
from ui.rules_window import (
    DictionaryInspection,
    RuleManagerDialog,
    RuleWindowResult,
    _configure_rule_table,
    _conflict_summary,
    _select_default_direction,
    inspect_dictionary,
    review_import,
)
from ui.i18n import Translator
from ui.i18n import configuration_label
from ui import rules_window


class Signal:
    def connect(self, _callback):
        return None


class Combo:
    def __init__(self, value):
        self.value = value

    def currentData(self):
        return self.value


class Edit:
    def __init__(self, value=""):
        self.value = value
        self.enabled = True

    def text(self):
        return self.value

    def setText(self, value):
        self.value = value

    def clear(self):
        self.value = ""

    def setEnabled(self, value):
        self.enabled = value


class Spin:
    def __init__(self, value=100):
        self._value = value

    def value(self):
        return self._value


class Table:
    def __init__(self, row=0):
        self.selected = row
        self.rows = []

    def currentRow(self):
        return self.selected

    def setRowCount(self, count):
        self.rows = self.rows[:count]

    def rowCount(self):
        return len(self.rows)

    def insertRow(self, index):
        self.rows.insert(index, [])

    def setItem(self, row, column, item):
        while len(self.rows[row]) <= column:
            self.rows[row].append(None)
        self.rows[row][column] = item

    def selectRow(self, row):
        self.selected = row


class Button:
    def __init__(self):
        self.enabled = True

    def setEnabled(self, value):
        self.enabled = value


class ConflictItem:
    def __init__(self, text):
        self.text = text
        self.values = {}

    def setData(self, key, value):
        self.values[key] = value

    def data(self, key):
        return self.values.get(key)


class ConflictList:
    def __init__(self):
        self.items = []

    def clear(self):
        self.items.clear()

    def addItem(self, item):
        self.items.append(item)


class QMessageBox:
    @staticmethod
    def warning(*_args):
        raise AssertionError("valid test rule should not trigger a warning")


def _fake_widget_tree(value):
    if isinstance(value, fake_qt.Layout):
        for child in value.children:
            yield from _fake_widget_tree(child)
    elif isinstance(value, fake_qt.Base):
        yield value
        layout = getattr(value, "_layout", None)
        if layout is not None:
            yield from _fake_widget_tree(layout)
        for child in value.__dict__.get("_children", ()):
            yield from _fake_widget_tree(child)


def _manager(rules, *, config="s2t", row=0, rule_type="exact", source="术语", target="新词"):
    manager = object.__new__(RuleManagerDialog)
    manager._run_ruleset_ids = ()
    manager._qt = SimpleNamespace(
        Qt=SimpleNamespace(UserRole=32),
        QListWidgetItem=ConflictItem,
        QTableWidgetItem=lambda value: value,
        QMessageBox=QMessageBox,
    )
    manager._labels = {"title": "Rules"}
    manager._translator = Translator("en")
    manager.rules = list(rules)
    manager._profile_id = "profile"
    manager._book_fingerprint = "book-hash"
    manager._config = config
    manager.table = Table(row)
    manager.conflict_list = ConflictList()
    manager.apply_button = Button()
    manager.update_button = Button()
    manager.type_combo = Combo(rule_type)
    manager.match_type_combo = Combo("literal")
    manager.direction_combo = Combo(config)
    manager.source_edit = Edit(source)
    manager.target_edit = Edit(target)
    manager.scope_combo = Combo("global")
    manager.priority_edit = Spin()
    return manager


def test_update_selected_replaces_rule_without_creating_conflict():
    original = Rule(id="stable-id", source="术语", target="旧词", direction="s2t",
                    created_at="2024-01-01T00:00:00Z", updated_at="2024-01-01T00:00:00Z")
    manager = _manager((original,))

    manager._update_selected()

    assert len(manager.rules) == 1
    assert manager.rules[0].id == "stable-id"
    assert manager.rules[0].created_at == original.created_at
    assert manager.rules[0].target == "新词"
    assert manager.rules[0].updated_at != original.updated_at
    assert manager.conflict_list.items == []
    assert manager.apply_button.enabled


def test_update_preserves_rule_owner_version_and_annotations():
    original = Rule(
        id="owned-id", source="术语", target="旧词", direction="s2t", scope="book",
        book_fingerprint="book-A", semantic_version=1, comment="Comment",
        source_note="Source note", created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )
    manager = _manager((original,), source="术语", target="新词")
    manager.scope_combo = Combo("book")
    manager._book_fingerprint = "book-B"
    manager._rulesets = {"default": RuleSet("default", semantic_version=1)}
    manager._ruleset_id = "default"

    manager._update_selected()

    updated = manager.rules[0]
    assert updated.id == original.id
    assert updated.book_fingerprint == "book-A"
    assert updated.semantic_version == 1
    assert updated.comment == "Comment"
    assert updated.source_note == "Source note"
    assert updated.created_at == original.created_at
    assert updated.updated_at != original.updated_at


def test_explicitly_changing_scope_to_current_book_binds_current_book():
    original = Rule(
        id="owned-id", source="术语", target="旧词", direction="s2t", scope="global",
        semantic_version=2, action="replace", stage="pre",
    )
    manager = _manager((original,), source="术语", target="新词", rule_type="replace_post")
    manager.scope_combo = Combo("book")
    manager._book_fingerprint = "book-B"
    manager._rulesets = {"default": RuleSet("default", semantic_version=2)}
    manager._ruleset_id = "default"

    manager._update_selected()

    assert manager.rules[0].book_fingerprint == "book-B"
    assert manager.rules[0].stage == "post"


def test_add_appends_new_rule_and_protect_uses_source_as_target():
    manager = _manager(())
    manager._add()
    assert len(manager.rules) == 1
    assert manager.rules[0].source == "术语"

    protected = _manager((), rule_type="protect", source="保护词", target="ignored")
    protected._type_changed()
    assert not protected.target_edit.enabled
    assert protected.target_edit.value == ""
    protected._add()
    assert protected.rules[0].type == "protect"
    assert protected.rules[0].target == "保护词"


def test_enter_in_rule_editor_submits_without_opening_ruleset_prompt():
    qt = make_with_table()
    qt.QInputDialog = SimpleNamespace(
        getText=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Enter should not open the ruleset prompt")
        )
    )
    manager = RuleManagerDialog(qt, (), translator=Translator("en"))
    manager.source_edit.setText("术语")
    manager.target_edit.setText("新词")

    manager.source_edit.returnPressed.emit()

    assert len(manager.rules) == 1
    assert manager.rules[0].source == "术语"
    assert manager.rules[0].target == "新词"
    assert manager.table.rowCount() == 1
    assert all(
        button.autoDefault() is False
        for button in (
            manager.new_ruleset_button,
            manager.rename_ruleset_button,
            manager.add_button,
            manager.update_button,
            manager.remove_button,
            manager.template_button,
            manager.test_button,
            manager.inspect_button,
            manager.ruleset_settings_close_button,
            manager.apply_button,
            manager.cancel_button,
        )
    )


@pytest.mark.parametrize(
    ("visible_rule_ids", "selected_row"),
    [(["r-a", "r-b"], 1), (["r-b"], 0)],
)
def test_inspect_without_input_uses_the_visible_selected_rule(
    monkeypatch, visible_rule_ids, selected_row,
):
    rules = (
        Rule(id="r-a", direction="s2t", source="甲方", target="甲方案"),
        Rule(id="r-b", direction="s2t", source="乙方", target="乙方案"),
    )
    manager = _manager(rules, row=selected_row)
    manager._visible_rule_ids = visible_rule_ids
    manager._official_convert = lambda _config, value: value
    manager._resolve_editor_draft = lambda: True
    manager._sandbox_snapshot = lambda: (None, "sandbox")
    manager.test_input = SimpleNamespace(toPlainText=lambda: "")
    manager.test_context_label = Edit()
    manager._comparison_configs = ()
    manager._ui_preferences = {}
    manager._save_ui_preferences = None
    manager.dialog = object()
    manager._labels["operation_failed"] = "Operation failed"
    seen = {}
    monkeypatch.setattr(
        rules_window,
        "show_dictionary_inspector",
        lambda text, **_kwargs: seen.setdefault("text", text),
    )

    manager._inspect()

    assert seen["text"] == "乙方"


def test_reject_confirms_unsaved_rules_and_returning_keeps_window_open():
    manager = RuleManagerDialog(make_with_table(), (), translator=Translator("en"))
    manager.source_edit.setText("术语")
    manager.target_edit.setText("新词")
    manager._add()
    confirm_calls = []
    manager._confirm_discard_rules = lambda: confirm_calls.append(True) or False

    manager.dialog.reject()

    assert confirm_calls == [True]
    assert manager.dialog.result is None
    assert manager.dialog.isVisible()


def test_reject_without_rule_changes_does_not_prompt():
    manager = RuleManagerDialog(make_with_table(), (), translator=Translator("en"))
    confirm_calls = []
    manager._confirm_discard_rules = lambda: confirm_calls.append(True) or True

    manager.dialog.reject()

    assert confirm_calls == []
    assert manager.dialog.result == 0


def test_rule_table_and_default_ruleset_use_localized_labels():
    qt = make_with_table()
    rule = Rule(id="localized", source="术语", target="专名", direction="s2t")
    wildcard = Rule(
        id="wildcard", type="protect", source="受保护", direction="*"
    )
    translator = Translator("zh-Hans")
    manager = RuleManagerDialog(qt, (rule, wildcard), translator=translator)

    assert manager.table.item(0, 0).text() == (
        translator.text("rules.exact") + " · " + translator.text("rules.literal"))
    assert manager.table.item(0, 1).text() == configuration_label(translator, "s2t")
    assert manager.table.item(1, 0).text() == (
        translator.text("rules.protect") + " · " + translator.text("rules.literal"))
    assert manager.table.item(1, 1).text() == translator.text("rules.direction_any")
    any_index = manager.direction_combo.findData("*")
    assert manager.direction_combo.itemText(any_index) == translator.text("rules.direction_any")
    assert manager.ruleset_combo.itemText(0) == translator.text("rules.default_set_name")
    assert manager.new_ruleset_button.text() == translator.text("rules.new_set")
    assert manager._ruleset_menu_actions["help"].text() == translator.text(
        "rules.help_details")


def test_rule_conflicts_and_sandbox_have_dedicated_tabs():
    manager = RuleManagerDialog(make_with_table(), (), translator=Translator("en"))

    assert manager.conflicts_label.text() == Translator("en").text(
        "rules.conflicts_count", count=0)
    assert manager.conflict_list.maximumHeight() == 120
    assert not manager.test_box.isCheckable()
    assert any(call[0] == "addTab" for call in manager.tabs.calls)


def test_rules_page_has_no_checkable_disclosure_groupboxes():
    manager = RuleManagerDialog(make_with_table(), (), translator=Translator("en"))

    groupboxes = [
        widget for widget in _fake_widget_tree(manager.rules_page)
        if isinstance(widget, manager._qt.QGroupBox)
    ]
    assert groupboxes
    assert all(not group.isCheckable() for group in groupboxes)


def test_more_menu_exposes_settings_help_import_bulk_export_and_delete(monkeypatch):
    triggered = []
    handlers = {
        "settings": "_open_ruleset_settings",
        "help": "_show_ruleset_help",
        "import": "_import",
        "bulk_add": "_bulk_add",
        "export": "_export",
        "delete": "_delete_ruleset",
    }
    for name, method in handlers.items():
        monkeypatch.setattr(
            RuleManagerDialog, method,
            lambda _self, selected=name: triggered.append(selected))
    manager = RuleManagerDialog(
        make_with_table(), (), translator=Translator("en"),
        rulesets=(RuleSet("default"), RuleSet("mine")), ruleset_id="mine")

    assert manager.ruleset_more_button.menu() is manager.ruleset_menu
    assert manager.ruleset_more_button.popupMode() == manager._qt.QToolButton.InstantPopup
    assert set(manager._ruleset_menu_actions) == {
        "settings", "help", "import", "bulk_add", "export", "delete",
    }
    assert len(manager.ruleset_menu.actions()) == 6
    for action in manager._ruleset_menu_actions.values():
        action.trigger()
    assert set(triggered) == set(handlers)
    settings_form = manager.ruleset_settings_dialog._layout.children[0]
    settings_controls = {
        widget
        for row in settings_form.children
        for widget in row
        if isinstance(widget, fake_qt.Base)
    }
    assert {
        manager.default_direction_combo,
        manager.default_scope_combo,
        manager.ruleset_enabled_check,
    } <= settings_controls


def test_test_page_places_input_before_test_buttons():
    manager = RuleManagerDialog(make_with_table(), (), translator=Translator("en"))
    children = manager.test_content._layout.children
    buttons_index = next(
        index for index, child in enumerate(children)
        if isinstance(child, fake_qt.Layout) and manager.test_button in child.children
    )

    assert children.index(manager.test_input) < buttons_index


def test_rules_editor_labels_are_buddied_and_table_has_accessible_name():
    manager = RuleManagerDialog(make_with_table(), (), translator=Translator("en"))

    children = manager.editor_form.children
    assert len(children) == 16
    assert all(children[index].buddy() is children[index + 1] for index in range(0, 14, 2))
    assert manager.table.accessibleName()


def test_rules_window_minimum_height_fits_common_screen():
    manager = RuleManagerDialog(make_with_table(), (), translator=Translator("en"))
    hint = manager.dialog.minimumSizeHint()
    if hint is None:
        pytest.skip("fake Qt does not calculate widget layout sizes")

    assert hint.height() < 600


def test_direction_default_is_selected_from_current_config():
    class DirectionCombo:
        def __init__(self):
            self.items = ["s2t", "t2s"]
            self.selected = None

        def findData(self, value):
            return self.items.index(value) if value in self.items else -1

        def setCurrentIndex(self, index):
            self.selected = self.items[index]

    combo = DirectionCombo()
    _select_default_direction(combo, "t2s")
    assert combo.selected == "t2s"


def test_new_rule_in_fresh_default_set_uses_current_direction():
    manager = RuleManagerDialog(
        make_with_table(), (), translator=Translator("en"), config="s2t",
        rulesets=(RuleSet("default"),), ruleset_id="default",
    )

    assert manager.direction_combo.currentData() == "s2t"
    manager.source_edit.setText("里")
    manager.target_edit.setText("裡")
    manager._add()

    assert manager.rules[-1].direction == "s2t"


def test_wildcard_direction_shows_reverse_warning():
    wildcard = Rule(id="wildcard", source="里", target="裡", direction="*")
    manager = RuleManagerDialog(
        make_with_table(), (wildcard,), translator=Translator("en"), config="s2t",
        rulesets=(RuleSet("default", (wildcard,)),), ruleset_id="default",
    )
    manager.table.selectRow(0)
    manager._load_selected()
    manager._refresh_selection_details()

    warning = Translator("en").text("rules.wildcard_direction_warning")
    assert warning in manager.editor_mode_label.text()
    assert warning in manager.selection_details.toPlainText()

    manager.direction_combo.setCurrentIndex(manager.direction_combo.findData("s2t"))
    assert warning not in manager.editor_mode_label.text()


def test_rule_table_is_not_editable_and_conflict_can_select_a_rule():
    class View:
        NoEditTriggers = 0
        SelectRows = 1

    class EditableTable:
        def __init__(self):
            self.edit_triggers = None
            self.selection = None

        def setEditTriggers(self, value):
            self.edit_triggers = value

        def setSelectionBehavior(self, value):
            self.selection = value

    table = EditableTable()
    _configure_rule_table(table, SimpleNamespace(QAbstractItemView=View))
    assert table.edit_triggers == View.NoEditTriggers
    assert table.selection == View.SelectRows

    conflict = (
        Rule(id="one", source="词", target="甲", direction="s2t"),
        Rule(id="two", source="词", target="乙", direction="s2t"),
    )
    manager = _manager(conflict)
    manager._refresh()
    assert manager.conflict_list.items
    manager._select_conflict_item(manager.conflict_list.items[0])
    assert manager.table.currentRow() == 0


def test_rule_conflict_summary_localizes_kind_and_preserves_source():
    conflict = find_conflicts((
        Rule(id="one", source="词", target="甲", direction="s2t"),
        Rule(id="two", source="词", target="乙", direction="s2t"),
    ))[0]
    for language in ("en", "zh-Hans", "zh-Hant"):
        summary = _conflict_summary(conflict, Translator(language))
        assert "词" in summary
        assert "SAME_SOURCE_DIFFERENT_TARGET" not in summary


def test_conflict_with_another_run_ruleset_is_listed_and_blocks_save():
    current = Rule(id="a1", source="软件", target="軟體", direction="s2t")
    other = Rule(id="b1", source="软件", target="軟件", direction="s2t")
    manager = RuleManagerDialog(
        make_with_table(), (current,), translator=Translator("en"),
        run_options={"ruleset_ids": ["A", "B"]},
        run_ruleset_ids=("A", "B"),
        rulesets=(
            RuleSet("A", (current,), name="Current terms"),
            RuleSet("B", (other,), name="Other terms"),
        ),
        ruleset_id="A",
    )

    assert manager.conflict_list.count() == 1
    assert "Other terms" in manager.conflict_list.item(0).text()
    assert "a1" in manager.conflict_list.item(0).text()
    assert "b1" in manager.conflict_list.item(0).text()
    assert not manager.apply_button.isEnabled()


def test_unselected_ruleset_conflict_does_not_block_save():
    current = Rule(id="a1", source="软件", target="軟體", direction="s2t")
    other = Rule(id="b1", source="软件", target="軟件", direction="s2t")
    manager = RuleManagerDialog(
        make_with_table(), (current,), translator=Translator("en"),
        run_options={"ruleset_ids": ["A"]},
        run_ruleset_ids=("A",),
        rulesets=(RuleSet("A", (current,)), RuleSet("B", (other,))),
        ruleset_id="A",
    )

    assert manager.conflict_list.count() == 0
    assert manager.apply_button.isEnabled()


def test_use_in_run_checkbox_tracks_selected_ruleset():
    manager = RuleManagerDialog(
        make_with_table(), (), translator=Translator("en"),
        rulesets=(RuleSet("A"), RuleSet("B")), ruleset_id="A",
        run_ruleset_ids=("A",))

    assert manager.use_in_run_check.isChecked()
    manager.ruleset_combo.setCurrentIndex(manager.ruleset_combo.findData("B"))
    assert not manager.use_in_run_check.isChecked()
    manager.use_in_run_check.setChecked(True)

    assert manager._run_ruleset_ids == ("A", "B")
    manager._apply()
    assert isinstance(manager.result, RuleWindowResult)
    assert manager.result.run_ruleset_ids == ("A", "B")


def test_disabling_shared_ruleset_restores_check_when_confirmation_is_cancelled(monkeypatch):
    manager = RuleManagerDialog(
        make_with_table(), (), translator=Translator("en"), profile_id="current",
        rulesets=(RuleSet("shared"),), ruleset_id="shared",
        ruleset_profiles={"shared": (("other", "Other profile"),)})
    prompts = []
    monkeypatch.setattr(
        rules_window, "ask_confirmation",
        lambda _qt, _parent, _title, message, _translator: (prompts.append(message), False)[1],
    )

    assert "Other profile" in manager.ruleset_enabled_check.toolTip()
    manager.ruleset_enabled_check.setChecked(False)

    assert len(prompts) == 1
    assert manager.ruleset_enabled_check.isChecked()
    assert manager._rulesets["shared"].enabled


def test_default_ruleset_cannot_be_deleted():
    manager = RuleManagerDialog(
        make_with_table(), (), translator=Translator("en"),
        rulesets=(RuleSet("default"),), ruleset_id="default")

    action = manager._ruleset_menu_actions["delete"]
    assert not action.isEnabled()
    assert action.toolTip() == manager._labels["cannot_delete_default"]
    manager._delete_ruleset()
    assert tuple(manager._rulesets) == ("default",)
    assert manager._deleted == []


def test_cancel_after_delete_keeps_ruleset_file(monkeypatch, tmp_path):
    store = RuleStore(tmp_path / "rules")
    store.save(RuleSet("mine"))
    manager = RuleManagerDialog(
        make_with_table(), (), translator=Translator("en"),
        rulesets=(RuleSet("default"), RuleSet("mine", name="Mine")),
        ruleset_id="mine", rule_store=store,
        ruleset_profiles={"mine": (("saved", "Saved"),)})
    prompts = []
    monkeypatch.setattr(
        rules_window, "ask_confirmation",
        lambda _qt, _parent, _title, message, _translator: (prompts.append(message), True)[1],
    )

    manager._delete_ruleset()

    assert len(prompts) == 1
    assert "Saved" in prompts[0]
    assert manager._deleted == ["mine"]
    assert store.load("mine").id == "mine"
    manager._confirm_discard_rules = lambda: True
    manager.cancel_button.click()
    assert manager.result is None
    assert store.load("mine").id == "mine"


def test_foreign_book_rule_is_labelled_other_book():
    rule = Rule(
        id="other-book", source="术语", target="专名", direction="s2t",
        scope="book", book_fingerprint="old-book")
    manager = RuleManagerDialog(
        make_with_table(), (rule,), translator=Translator("en"),
        profile_id="current-profile", book_fingerprint="current-book",
        run_ruleset_ids=("default",))
    manager.table.selectRow(0)
    manager._refresh_selection_details()

    assert manager.table.item(0, 4).text() == Translator("en").text(
        "rules.scope_book_other")
    assert Translator("en").text("rules.scope_book_other") in (
        manager.selection_details.toPlainText())
    assert manager.foreign_owner_button.isVisible()
    manager.foreign_owner_button.click()
    assert manager.activity_filter.currentData() == "inactive"
    assert manager._visible_rule_ids == ["other-book"]


def test_foreign_profile_rule_is_labelled_other_profile():
    rule = Rule(
        id="other-profile", source="术语", target="专名", direction="s2t",
        scope="profile", profile_id="old-profile")
    manager = RuleManagerDialog(
        make_with_table(), (rule,), translator=Translator("en"),
        profile_id="current-profile")

    assert manager.table.item(0, 4).text() == Translator("en").text(
        "rules.scope_profile_other")


def test_rebind_button_binds_current_book_only_on_click():
    rule = Rule(
        id="other-book", source="术语", target="专名", direction="s2t",
        scope="book", book_fingerprint="old-book",
        updated_at="2024-01-01T00:00:00Z")
    manager = RuleManagerDialog(
        make_with_table(), (rule,), translator=Translator("en"),
        profile_id="current-profile", book_fingerprint="current-book")
    manager.table.selectRow(0)
    manager._load_selected()

    assert manager.rules[0].book_fingerprint == "old-book"
    assert manager.rebind_owner_button.isVisible()
    assert manager.rebind_owner_button.isEnabled()
    manager.rebind_owner_button.click()

    assert manager.rules[0].book_fingerprint == "current-book"
    assert manager.rules[0].updated_at != "2024-01-01T00:00:00Z"
    assert not manager.rebind_owner_button.isVisible()


def test_rebind_button_is_disabled_when_current_book_is_unavailable():
    rule = Rule(
        id="other-book", source="术语", target="专名", direction="s2t",
        scope="book", book_fingerprint="old-book")
    manager = RuleManagerDialog(
        make_with_table(), (rule,), translator=Translator("en"),
        profile_id="current-profile", book_fingerprint=None)
    manager.table.selectRow(0)
    manager._load_selected()

    assert manager.rebind_owner_button.isVisible()
    assert not manager.rebind_owner_button.isEnabled()


def test_rebind_button_binds_current_profile():
    rule = Rule(
        id="other-profile", source="术语", target="专名", direction="s2t",
        scope="profile", profile_id="old-profile",
        updated_at="2024-01-01T00:00:00Z")
    manager = RuleManagerDialog(
        make_with_table(), (rule,), translator=Translator("en"),
        profile_id="current-profile")
    manager.table.selectRow(0)
    manager._load_selected()

    assert manager.rebind_owner_button.isEnabled()
    manager.rebind_owner_button.click()

    assert manager.rules[0].profile_id == "current-profile"
    assert manager.rules[0].updated_at != "2024-01-01T00:00:00Z"


@pytest.mark.parametrize("semantic_version", (1, 2))
def test_import_tsv_uses_target_ruleset_semantic_version(tmp_path, semantic_version):
    store = RuleStore(tmp_path / "rules")
    store.save(RuleSet("B", semantic_version=semantic_version))
    imported_path = tmp_path / "rules.tsv"
    imported_path.write_text(
        "direction\tsource\ttarget\ns2t\t软件\t軟件\n", encoding="utf-8")
    manager = object.__new__(RuleManagerDialog)
    manager._translator = Translator("en")
    manager._qt = SimpleNamespace(
        QFileDialog=SimpleNamespace(getOpenFileName=lambda *_args: (str(imported_path), "")),
    )
    manager._labels = {"import": "Import"}
    manager._rule_store = store
    rulesets, errors = store.list()
    assert errors == ()
    manager._rulesets = {item.id: item for item in rulesets}
    manager._ruleset_id = "B"
    manager.rules = []
    manager._run_options = {"ruleset_ids": ["B"]}
    manager._config = "s2t"
    manager._profile_id = None
    manager._book_fingerprint = None
    manager.dialog = object()
    manager._ui_preferences = {}
    manager._save_ui_preferences = None
    manager._import_options = lambda _path: {
        "format": "tsv", "direction": "s2t", "scope": "global", "strict": True,
    }
    manager._confirm_import = lambda _review: True
    manager._refresh = lambda: None
    manager._show_exception = lambda error: (_ for _ in ()).throw(error)

    manager._import()

    assert len(manager.rules) == 1
    assert manager.rules[0].semantic_version == semantic_version
    assert (manager.rules[0].action, manager.rules[0].match_type,
            manager.rules[0].stage) == ("override", "literal", "source")


def test_json_import_options_scope_is_default_and_rebind_is_opt_in(monkeypatch):
    manager = RuleManagerDialog(
        make_with_table(), (), translator=Translator("en"), config="s2t",
        profile_id="profile-A", book_fingerprint="book-A")
    state = {}

    def accept_json_options(dialog):
        form = dialog._layout.children[0]
        scope_label, _scope_combo = form.children[2]
        rebind_owner = form.children[3][0]
        state["scope_label"] = scope_label.text()
        state["rebind_default"] = rebind_owner.isChecked()
        state["rebind_visible"] = rebind_owner.isVisible()
        rebind_owner.setChecked(True)
        dialog._layout.children[-1].children[-1].clicked.emit()

    monkeypatch.setattr(rules_window, "exec_dialog", accept_json_options)
    options = manager._import_options("rules.json")

    assert state == {
        "scope_label": "Only for records without a scope",
        "rebind_default": False,
        "rebind_visible": True,
    }
    assert options["scope"] == "global"
    assert options["rebind_owner"] is True


def test_bulk_paste_adds_rules_through_import_review(monkeypatch):
    manager = RuleManagerDialog(
        make_with_table(), (), translator=Translator("en"), config="s2t",
        profile_id="profile-A", book_fingerprint="book-A")
    manager.scope_combo.setCurrentIndex(manager.scope_combo.findData("book"))
    reviews = []
    manager._confirm_import = lambda review: (reviews.append(review), True)[1]

    def accept_bulk_dialog(dialog):
        editor = next(
            child for child in dialog._layout.children
            if isinstance(child, manager._qt.QPlainTextEdit))
        editor.setPlainText("软件=軟件\n詞語→詞彙\n软件=軟件")
        dialog._layout.children[-1].children[-1].clicked.emit()

    monkeypatch.setattr(rules_window, "exec_dialog", accept_bulk_dialog)
    manager._bulk_add()

    assert len(reviews) == 1
    assert len(reviews[0].additions) == 2
    assert reviews[0].duplicate_count == 1
    assert [(rule.direction, rule.scope, rule.source, rule.target)
            for rule in manager.rules] == [
                ("s2t", "book", "软件", "軟件"),
                ("s2t", "book", "詞語", "詞彙"),
            ]


def test_bulk_paste_cancel_keeps_rules_unchanged(monkeypatch):
    original = Rule(id="existing", source="旧词", target="新词", direction="s2t")
    manager = RuleManagerDialog(
        make_with_table(), (original,), translator=Translator("en"), config="s2t")
    before = tuple(manager.rules)

    def cancel_bulk_dialog(dialog):
        editor = next(
            child for child in dialog._layout.children
            if isinstance(child, manager._qt.QPlainTextEdit))
        editor.setPlainText("another=rule")
        dialog._layout.children[-1].children[-2].clicked.emit()

    monkeypatch.setattr(rules_window, "exec_dialog", cancel_bulk_dialog)
    manager._bulk_add()

    assert tuple(manager.rules) == before


def test_rule_details_show_legacy_precedence_version():
    translator = Translator("zh-Hans")
    legacy_rule = Rule(
        id="legacy", semantic_version=1, source="词", target="詞", direction="s2t")
    manager = RuleManagerDialog(
        make_with_table(), (legacy_rule,), translator=translator, config="s2t")
    manager.table.selectRow(0)
    manager._refresh_selection_details()

    expected = translator.text(
        "rules.detail_version", version=translator.text("rules.version_v1"))
    assert expected in manager.selection_details.toPlainText()


def test_nonstrict_txt_import_reports_candidates_and_invalid_rows_with_scope():
    imported = import_rules(
        "术语\t专名 其他候选\n空目标\t\n",
        format="txt",
        direction="s2t",
        scope="profile",
        profile_id="current-profile",
        strict=False,
    )

    assert len(imported.rules) == 1
    assert imported.rules[0].scope == "profile"
    assert imported.rules[0].profile_id == "current-profile"
    assert len(imported.diagnostics) == 2
    assert [item.severity for item in imported.diagnostics] == ["warning", "error"]


def test_import_review_counts_existing_rules_as_duplicates_without_adding():
    existing = Rule(id="existing", source="术语", target="专名", direction="s2t")
    imported = import_rules(
        '[{"type":"exact","direction":"s2t","source":"术语","target":"专名"}]',
        format="json",
    )

    review = review_import((existing,), imported)

    assert review.additions == ()
    assert review.duplicate_count == 1


def test_import_reassigns_ids_colliding_with_any_saved_ruleset(tmp_path):
    store = RuleStore(tmp_path)
    original = Rule(id="shared", source="术语", target="专名", direction="s2t")
    store.save(RuleSet("A", (original,)))
    payload = export_rules((original,), format="json")
    store.save(RuleSet("A", (Rule(
        id="shared", source="术语", target="专名", direction="s2t", enabled=False,
    ),)))
    store.save(RuleSet("B"))
    imported_path = tmp_path / "rules.json"
    imported_path.write_text(payload, encoding="utf-8")

    manager = object.__new__(RuleManagerDialog)
    manager._translator = Translator("en")
    manager._qt = SimpleNamespace(
        QFileDialog=SimpleNamespace(getOpenFileName=lambda *_args: (str(imported_path), "")),
    )
    manager._labels = {"import": "Import"}
    manager._rule_store = store
    manager._rulesets = {}
    saved, errors = store.list()
    assert errors == ()
    manager._rulesets = {item.id: item for item in saved}
    manager._rulesets["B"] = RuleSet("B")
    manager._ruleset_id = "B"
    manager._run_options = {}
    manager._config = "s2t"
    manager._book_fingerprint = None
    manager._profile_id = None
    manager.rules = []
    manager.dialog = object()
    manager._profile_id = None
    manager._book_fingerprint = None
    manager._import_options = lambda _path: {
        "format": "json", "direction": "s2t", "scope": "global", "strict": True,
    }
    reviews = []
    manager._confirm_import = lambda review: (reviews.append(review), True)[1]
    manager._refresh = lambda: None
    manager._show_exception = lambda error: (_ for _ in ()).throw(error)

    manager._import()

    assert len(manager.rules) == 1
    assert manager.rules[0].id != "shared"
    assert reviews[0].id_reassigned_count == 1


def test_import_review_includes_conflicts_from_other_run_rulesets(tmp_path):
    existing = Rule(id="a1", source="软件", target="軟體", direction="s2t")
    imported_rule = Rule(id="b1", source="软件", target="軟件", direction="s2t")
    store = RuleStore(tmp_path / "rules")
    store.save(RuleSet("A", (existing,), name="Other terms"))
    store.save(RuleSet("B", name="Current terms"))
    imported_path = tmp_path / "conflicting.json"
    imported_path.write_text(export_rules((imported_rule,), format="json"), encoding="utf-8")

    manager = object.__new__(RuleManagerDialog)
    manager._translator = Translator("en")
    manager._qt = SimpleNamespace(
        QFileDialog=SimpleNamespace(getOpenFileName=lambda *_args: (str(imported_path), "")),
    )
    manager._labels = {"import": "Import"}
    manager._rule_store = store
    saved, errors = store.list()
    assert errors == ()
    manager._rulesets = {item.id: item for item in saved}
    manager._ruleset_id = "B"
    manager.rules = []
    manager._run_options = {"ruleset_ids": ["A", "B"]}
    manager._run_ruleset_ids = ("A", "B")
    manager._config = "s2t"
    manager._profile_id = None
    manager._book_fingerprint = None
    manager.dialog = object()
    manager._ui_preferences = {}
    manager._save_ui_preferences = None
    manager._import_options = lambda _path: {
        "format": "json", "direction": "s2t", "scope": "global", "strict": True,
    }
    reviews = []
    manager._confirm_import = lambda review: (reviews.append(review), False)[1]
    manager._refresh = lambda: None
    manager._show_exception = lambda error: (_ for _ in ()).throw(error)

    manager._import()

    assert manager.rules == []
    assert len(reviews) == 1
    assert any(
        {rule.id for rule in conflict.rules} == {"a1", "b1"} and conflict.blocking
        for conflict in reviews[0].conflicts
    )


def test_export_confirms_before_writing_a_lossy_format(monkeypatch, tmp_path):
    rule = Rule(
        id="disabled", source="术语", target="专名", direction="s2t", enabled=False
    )
    destination = tmp_path / "rules.tsv"
    manager = object.__new__(RuleManagerDialog)
    manager._qt = SimpleNamespace(
        QFileDialog=SimpleNamespace(
            getSaveFileName=lambda *_args: (str(destination), "TSV")
        ),
    )
    manager._labels = {"export": "Export", "title": "Rules"}
    manager._translator = Translator("en")
    manager.dialog = object()
    manager.rules = [rule]
    prompts = []
    monkeypatch.setattr(
        rules_window,
        "ask_confirmation",
        lambda _qt, _parent, _title, message, _translator: (
            prompts.append(message), True
        )[1],
    )

    manager._export()

    assert len(prompts) == 1
    assert "matching mode, stage, scope, ownership, enabled state, or priority" in prompts[0]
    assert destination.read_text(encoding="utf-8").startswith("direction\tsource\ttarget\tcomment")


def test_tsv_export_warning_names_skipped_multiline_rules(monkeypatch, tmp_path):
    unsafe = Rule(
        id="multiline", source="两行\n原文", target="目标", direction="s2t")
    destination = tmp_path / "rules.tsv"
    manager = object.__new__(RuleManagerDialog)
    manager._qt = SimpleNamespace(QFileDialog=SimpleNamespace(
        getSaveFileName=lambda *_args: (str(destination), "TSV"),
    ))
    manager._labels = {"export": "Export", "title": "Rules"}
    manager._translator = Translator("en")
    manager.dialog = object()
    manager.rules = [unsafe]
    prompts = []
    monkeypatch.setattr(
        rules_window,
        "ask_confirmation",
        lambda _qt, _parent, _title, message, _translator: (
            prompts.append(message), True
        )[1],
    )

    manager._export()

    assert len(prompts) == 1
    assert "TSV cannot represent 1 rule(s)" in prompts[0]
    assert "两行" not in destination.read_text(encoding="utf-8")
    assert destination.read_text(encoding="utf-8").count("\n") == 1


def test_export_cancellation_does_not_replace_existing_file(monkeypatch, tmp_path):
    rule = Rule(
        id="replace", semantic_version=2, action="replace", stage="pre",
        direction="s2t", source="old", target="new",
    )
    destination = tmp_path / "rules.tsv"
    destination.write_text("keep this file", encoding="utf-8")
    manager = object.__new__(RuleManagerDialog)
    manager._qt = SimpleNamespace(QFileDialog=SimpleNamespace(
        getSaveFileName=lambda *_args: (str(destination), "TSV"),
    ))
    manager._labels = {"export": "Export", "title": "Rules"}
    manager._translator = Translator("en")
    manager.dialog = object()
    manager.rules = [rule]
    monkeypatch.setattr(rules_window, "ask_confirmation", lambda *_args: False)

    manager._export()

    assert destination.read_text(encoding="utf-8") == "keep this file"


def test_dictionary_inspection_applies_profile_rules_and_comparison_configs():
    rule = Rule(id="profile-rule", source="术语", target="专名", direction="s2twp",
                scope="profile", profile_id="current-profile")
    inspection = inspect_dictionary(
        "术语",
        config="s2twp",
        official_convert=lambda _config, value: value,
        comparison_configs=comparison_configs("s2twp"),
        snapshot=RuleSnapshot.freeze((rule,)),
        profile_id="current-profile",
    )

    assert inspection.matched_rules == ("profile-rule",)
    assert tuple(name for name, _value in inspection.comparisons) == ("s2t", "s2tw", "s2twp")


def test_dictionary_inspection_uses_the_full_run_conversion_options():
    inspection = inspect_dictionary(
        '“文字”︐', config="s2t", official_convert=lambda _config, value: value,
        run_options={"quotation_mode": "corner", "punctuation_mode": "horizontal"},
    )

    assert inspection.final == "「文字」,"


def test_sandbox_run_scope_uses_only_referenced_enabled_rulesets_and_current_context():
    active = Rule(id="active", source="旧词", target="新词", direction="s2t")
    disabled = Rule(id="disabled-rule", source="旧词", target="错误", direction="s2t")
    unrelated = Rule(id="unrelated", source="额外", target="不参与", direction="s2t")
    manager = RuleManagerDialog(
        make_with_table(), (), translator=Translator("en"),
        official_convert=lambda _config, value: value, config="s2t",
        profile_id="profile-A", book_fingerprint="book-A",
        rulesets=(
            RuleSet("active", (active,)),
            RuleSet("disabled", (disabled,), enabled=False),
            RuleSet("extra", (unrelated,)),
        ),
        ruleset_id="extra", run_options={"ruleset_ids": ["active", "disabled"]},
        run_ruleset_ids=("active", "disabled"),
    )
    current_snapshot, current_context = manager._sandbox_snapshot()
    assert unrelated in current_snapshot.rules
    assert active not in current_snapshot.rules
    assert "not included in this conversion" in current_context

    manager.test_scope_combo.setCurrentIndex(manager.test_scope_combo.findData("run"))
    run_snapshot, run_context = manager._sandbox_snapshot()
    assert active in run_snapshot.rules
    assert disabled not in run_snapshot.rules
    assert unrelated not in run_snapshot.rules
    assert "active" in run_context

    inspection = inspect_dictionary(
        "旧词", config="s2t", official_convert=lambda _config, value: value,
        snapshot=run_snapshot, profile_id="profile-A", book_fingerprint="book-A",
    )
    assert inspection.final == "新词"
    assert inspection.matched_rules == ("active",)


def test_sandbox_result_is_marked_stale_after_input_or_scope_changes():
    manager = RuleManagerDialog(
        make_with_table(), (), translator=Translator("en"),
        official_convert=lambda _config, value: value, config="s2t",
    )
    manager.test_input.setPlainText("first input")
    manager._test()
    assert manager._test_result_has_run
    assert not manager.test_result_status.isVisible()

    manager.test_input.setPlainText("changed input")
    manager._mark_test_result_stale()
    assert manager.test_result_status.isVisible()
    assert "out of date" in manager.test_result_status.text()

    manager._mark_test_result_current()
    manager.test_scope_combo.setCurrentIndex(
        manager.test_scope_combo.findData("run"))
    manager._mark_test_result_stale()
    assert manager.test_result_status.isVisible()


def test_sandbox_scope_excludes_direction_and_owner_mismatches():
    rules = (
        Rule(id="direction", source="旧词", target="错向", direction="t2s"),
        Rule(id="owner", source="旧词", target="错书", direction="s2t",
             scope="book", book_fingerprint="other-book"),
    )
    inspection = inspect_dictionary(
        "旧词", config="s2t", official_convert=lambda _config, value: value,
        snapshot=RuleSnapshot.freeze(rules), profile_id="profile-A", book_fingerprint="book-A",
    )
    assert inspection.final == "旧词"
    assert inspection.matched_rules == ()


def test_dictionary_inspector_localizes_config_classification_and_rule_labels(monkeypatch):
    inspection = DictionaryInspection(
        input="軟體", config="s2tw", comparisons=(("s2t", "软件"),),
        final="軟體", matched_rules=("mine",), attribution="OpenCC:s2tw/comparative_config_diff",
        classifications=(SimpleNamespace(
            source="软件", target="軟體", category="regional",
            attribution_confidence="high", comparison_stage="s2tw-vs-s2t",
        ),),
    )
    qt = make_with_table()
    captured = []

    class CaptureText(qt.QPlainTextEdit):
        def __init__(self, *args):
            super().__init__(*args)
            captured.append(self)

    qt.QPlainTextEdit = CaptureText
    monkeypatch.setattr(rules_window, "load_qt", lambda: qt)
    monkeypatch.setattr(rules_window, "ensure_application", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(rules_window, "exec_dialog", lambda *_args: None)
    monkeypatch.setattr(rules_window, "inspect_dictionary", lambda *_args, **_kwargs: inspection)

    rules_window.show_dictionary_inspector(
        "軟體", config="s2tw", official_convert=lambda *_args: "",
        translator=Translator("zh-Hans"),
    )
    text = captured[0].toPlainText()

    assert "s2tw" not in text
    assert "regional" not in text
    assert "high" not in text
    assert "'软件'" not in text
    assert "命中规则：mine" in text


def test_ruleset_id_with_slash_is_rejected_with_localized_error():
    manager = object.__new__(RuleManagerDialog)
    manager.dialog = object()
    manager._labels = {"title": "Rules", "ruleset": "Rule set",
                       "invalid_ruleset": "localized invalid ID"}
    manager._rulesets = {}
    manager.rules = []
    manager._ruleset_id = "default"
    manager._renamed = []
    manager._qt = SimpleNamespace(
        QInputDialog=SimpleNamespace(getText=lambda *_args, **_kwargs: ("bad/name", True)),
        QMessageBox=SimpleNamespace(warning=lambda _parent, _title, message:
                                   setattr(manager, "warning", message)),
    )
    manager._warn = lambda message: setattr(manager, "warning", message)

    manager._new_ruleset()

    assert manager.warning == "localized invalid ID"
    assert manager._rulesets == {}


def test_switching_ruleset_stashes_edits_and_loads_selected_rules():
    first = Rule(id="first", source="甲", target="乙", direction="s2t")
    second = Rule(id="second", source="丙", target="丁", direction="s2t")
    manager = object.__new__(RuleManagerDialog)
    manager._ruleset_id = "one"
    manager._rulesets = {"one": RuleSet("one", (first,)),
                         "two": RuleSet("two", (second,))}
    manager.rules = [first]
    manager.ruleset_combo = SimpleNamespace(currentData=lambda: "two")
    manager._refresh = lambda: None

    manager._ruleset_changed()

    assert manager._ruleset_id == "two"
    assert manager.rules == [second]
    assert manager._rulesets["one"].rules == (first,)


def test_sandbox_lists_rule_id_source_target_and_match_location():
    rule = Rule(id="known-rule", source="术语", target="专名", direction="s2t")
    manager = RuleManagerDialog(
        make_with_table(), (rule,), translator=Translator("en"),
        official_convert=lambda _config, text: text, config="s2t",
        profile_id="profile", book_fingerprint="book-hash")
    manager.test_input.setPlainText("术语")

    manager._test()

    assert "known-rule: 术语 → 专名 at 0–2" in manager.test_output.toPlainText()
    assert "Hits: 1" in manager.test_output.toPlainText().splitlines()


def test_apply_saves_a_valid_unsubmitted_editor_draft():
    manager = RuleManagerDialog(make_with_table(), (), translator=Translator("en"))
    manager.source_edit.setText("draft source")
    manager.target_edit.setText("draft target")

    manager._apply()

    assert [(rule.source, rule.target) for rule in manager.rules] == [
        ("draft source", "draft target")]
    assert manager.accepted
    assert manager.dialog.result == 1


def test_apply_saves_editor_draft_into_managed_ruleset_result():
    manager = RuleManagerDialog(
        make_with_table(), (), translator=Translator("en"),
        rulesets=(RuleSet("terms"),), ruleset_id="terms")
    manager.source_edit.setText("saved source")
    manager.target_edit.setText("saved target")

    manager._apply()

    assert manager.result.rulesets[0].rules[0].source == "saved source"
    assert manager.result.rulesets[0].rules[0].target == "saved target"


def test_apply_keeps_an_invalid_editor_draft_open():
    manager = RuleManagerDialog(make_with_table(), (), translator=Translator("en"))
    manager.match_type_combo.setCurrentIndex(manager.match_type_combo.findData("regex"))
    manager.source_edit.setText("(?=x)")
    manager.target_edit.setText("bad")

    manager._apply()

    assert manager.rules == []
    assert not manager.accepted
    assert manager.dialog.result is None
    assert manager._editor_dirty()


def test_escape_returns_to_unsubmitted_rule_draft():
    manager = RuleManagerDialog(make_with_table(), (), translator=Translator("en"))
    manager.source_edit.setText("draft")
    manager.target_edit.setText("target")
    manager._ask_editor_draft_action = lambda: None

    assert manager._guard_reject() is False
    assert manager.source_edit.text() == "draft"
    assert manager.target_edit.text() == "target"
    assert manager.dialog.result is None


@pytest.mark.parametrize("action", ["apply", "discard", None])
def test_switching_table_rows_resolves_draft_without_changing_the_wrong_rule(action):
    first = Rule(id="first", source="one", target="old one", direction="s2t")
    second = Rule(id="second", source="two", target="old two", direction="s2t")
    manager = RuleManagerDialog(
        make_with_table(), (first, second), translator=Translator("en"))
    manager.table.selectRow(0)
    manager._selection_changed()
    manager.target_edit.setText("draft target")
    manager._ask_editor_draft_action = lambda: action
    manager.table.selectRow(1)

    manager._selection_changed()

    if action is None:
        assert manager._editing_rule_id == "first"
        assert manager.table.currentRow() == 0
        assert manager.target_edit.text() == "draft target"
    else:
        assert manager._editing_rule_id == "second"
        assert manager.target_edit.text() == "old two"
        assert manager.rules[1] == second
        if action == "apply":
            assert manager.rules[0].target == "draft target"
        else:
            assert manager.rules[0] == first


@pytest.mark.parametrize("action", ["apply", "discard", None])
def test_switching_rulesets_resolves_editor_draft(action):
    first = Rule(id="first", source="a", target="b", direction="s2t")
    manager = RuleManagerDialog(
        make_with_table(), (), translator=Translator("en"),
        rulesets=(RuleSet("one", (first,)), RuleSet("two")), ruleset_id="one")
    manager.source_edit.setText("draft")
    manager.target_edit.setText("target")
    manager._ask_editor_draft_action = lambda: action

    manager.ruleset_combo.setCurrentIndex(manager.ruleset_combo.findData("two"))

    if action is None:
        assert manager._ruleset_id == "one"
        assert manager.source_edit.text() == "draft"
    else:
        assert manager._ruleset_id == "two"
        assert manager.rules == []
        if action == "apply":
            assert [(rule.source, rule.target) for rule in manager._rulesets["one"].rules] == [
                ("a", "b"), ("draft", "target")]
        else:
            assert manager._rulesets["one"].rules == (first,)


def test_template_enter_adds_instead_of_overwriting_selected_rule():
    existing = Rule(id="existing", source="old", target="old target", direction="s2t")
    manager = RuleManagerDialog(make_with_table(), (existing,), translator=Translator("en"))
    manager.table.selectRow(0)
    manager._load_selected()
    manager._qt.QInputDialog = SimpleNamespace(getItem=lambda *_args, **_kwargs: (
        manager._labels["template_signature"], True))

    manager._fill_template()
    manager.source_edit.returnPressed.emit()

    assert manager.rules[0] == existing
    assert len(manager.rules) == 2
    assert manager.rules[1].action == "protect"
    assert manager._editing_rule_id is None


def test_search_and_filter_update_the_stable_rule_id_in_a_large_set():
    rules = tuple(Rule(
        id=f"rule-{index}", source=f"term-{index}", target=f"target-{index}",
        direction="s2t", comment=f"comment-{index:05d}") for index in range(10_000))
    manager = RuleManagerDialog(
        make_with_table(), rules, translator=Translator("en"), ruleset_id="active",
        rulesets=(RuleSet("active", rules),),
        run_options={"ruleset_ids": ["active"]},
        run_ruleset_ids=("active",),
    )
    original = {rule.id: rule for rule in manager.rules}
    manager.search_edit.setText("comment-00497")
    manager._filters_changed()

    assert manager.table.rowCount() == 1
    assert manager._visible_rule_ids == ["rule-497"]
    assert manager.count_label.text() == "Showing 1 of 10000"
    manager.table.selectRow(0)
    manager._selection_changed()
    assert manager._editing_rule_id == "rule-497"
    assert "Source: term-497" in manager.selection_details.toPlainText()
    manager.target_edit.setText("updated")
    manager._update_selected()
    manager.search_edit.setText("")
    manager._filters_changed()

    assert manager.table.rowCount() == 10_000
    changed = {rule.id: rule for rule in manager.rules}
    assert changed["rule-497"].target == "updated"
    assert all(changed[identifier] == original[identifier]
               for identifier in original if identifier != "rule-497")


def test_activity_filter_matches_rule_enabled_direction_scope_and_ruleset_state():
    rules = (
        Rule(id="active", source="a", target="b", direction="s2t"),
        Rule(id="disabled", source="c", target="d", direction="s2t", enabled=False),
        Rule(id="wrong-direction", source="e", target="f", direction="t2s"),
        Rule(id="wrong-owner", source="g", target="h", direction="s2t",
             scope="book", book_fingerprint="other-book"),
    )
    manager = RuleManagerDialog(
        make_with_table(), rules, translator=Translator("en"), ruleset_id="active-set",
        rulesets=(RuleSet("active-set", rules),),
        run_options={"ruleset_ids": ["active-set"]}, run_ruleset_ids=("active-set",),
        profile_id="profile-A",
        book_fingerprint="book-A",
    )
    manager.activity_filter.setCurrentIndex(manager.activity_filter.findData("active"))
    manager._filters_changed()
    assert manager._visible_rule_ids == ["active"]
    manager.activity_filter.setCurrentIndex(manager.activity_filter.findData("inactive"))
    manager._filters_changed()
    assert set(manager._visible_rule_ids) == {
        "disabled", "wrong-direction", "wrong-owner"}


@pytest.mark.parametrize("stage", ["pre", "post"])
def test_empty_target_is_displayed_as_deletion_and_roundtrips_unchanged(stage):
    deletion = Rule(
        id=f"delete-{stage}", semantic_version=2, action="replace", stage=stage,
        source="term", target="", direction="s2t")
    manager = RuleManagerDialog(make_with_table(), (deletion,), translator=Translator("en"))

    assert manager.table.item(0, 3).text() == Translator("en").text("rules.deleted_target")
    exported = export_rules(manager.rules)
    imported = import_rules(exported, format="json")
    assert imported.rules[0].target == ""


def test_protect_and_whitespace_targets_are_visually_distinct_from_deletion():
    protect = Rule(id="protect", type="protect", source="term", direction="s2t")
    whitespace = Rule(id="spaces", source="space", target="  ", direction="s2t")
    manager = RuleManagerDialog(
        make_with_table(), (protect, whitespace), translator=Translator("en"))

    assert manager.table.item(0, 3).text() == "term"
    assert "whitespace-only (2 chars): ␠␠" in manager.table.item(1, 3).text()
    assert "Whitespace-only targets: 1" in manager.target_warning_label.text()
