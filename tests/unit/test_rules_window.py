from types import SimpleNamespace
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
    manager.rules = list(rules)
    manager._profile_id = "profile"
    manager._book_fingerprint = "book-hash"
    manager._config = config
    manager.table = Table(row)
    manager.conflict_list = ConflictList()
    manager.apply_button = Button()
    manager.update_button = Button()
    manager.type_combo = Combo(rule_type)
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
            manager.import_button,
            manager.export_button,
            manager.test_button,
            manager.inspect_button,
            manager.apply_button,
            manager.cancel_button,
        )
    )


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
    monkeypatch.setattr(rules_window, "ensure_application", lambda *_args: None)
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
    assert "用户规则：mine" in text


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
    manager._rulesets = {"one": SimpleNamespace(id="one", rules=(first,), name=""),
                         "two": SimpleNamespace(id="two", rules=(second,), name="")}
    manager.rules = [first]
    manager.ruleset_combo = SimpleNamespace(currentData=lambda: "two")
    manager._refresh = lambda: None

    manager._ruleset_changed()

    assert manager._ruleset_id == "two"
    assert manager.rules == [second]
    assert manager._rulesets["one"].rules == (first,)


def test_sandbox_lists_rule_id_source_target_and_match_location():
    rule = Rule(id="known-rule", source="术语", target="专名", direction="s2t")
    manager = object.__new__(RuleManagerDialog)
    manager.rules = [rule]
    manager._official_convert = lambda _config, text: text
    manager._config = "s2t"
    manager._profile_id = "profile"
    manager._book_fingerprint = "book-hash"
    manager._labels = {
        "no_converter": "no converter", "original_label": "Original",
        "pre_rules_label": "Pre", "opencc_label": "OpenCC",
        "post_rules_label": "Post", "final_label": "Final", "hits_label": "Hits",
        "rule_hit": "{id}: {source} -> {target} at {start}-{end}",
        "no_hits": "No matches",
    }
    manager.test_input = SimpleNamespace(toPlainText=lambda: "术语")
    manager.test_output = SimpleNamespace(setPlainText=lambda text:
                                           setattr(manager, "output", text))

    manager._test()

    assert "known-rule: 术语 -> 专名 at 0-2" in manager.output
