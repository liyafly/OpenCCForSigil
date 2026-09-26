from types import SimpleNamespace
import pytest
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


def _manager(rules, *, config="s2t", row=0, rule_type="exact", source="术语", target="新词"):
    manager = object.__new__(RuleManagerDialog)
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
            manager.import_button,
            manager.export_button,
            manager.test_button,
            manager.inspect_button,
            manager.apply_button,
            manager.cancel_button,
        )
    )


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
    assert manager.help_label.text() == translator.text("rules.help")


def test_rule_conflicts_have_a_bounded_section_and_test_box_starts_collapsed():
    manager = RuleManagerDialog(make_with_table(), (), translator=Translator("en"))

    assert manager.conflicts_label.text() == Translator("en").text("rules.conflicts_title")
    assert manager.conflict_list.maximumHeight() == 120
    assert manager.test_box.isCheckable()
    assert not manager.test_box.isChecked()


def test_rules_editor_labels_are_buddied_and_table_has_accessible_name():
    manager = RuleManagerDialog(make_with_table(), (), translator=Translator("en"))

    children = manager.editor_form.children
    assert len(children) == 16
    assert all(children[index].buddy() is children[index + 1] for index in range(0, 16, 2))
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
