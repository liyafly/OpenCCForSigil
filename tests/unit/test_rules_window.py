from types import SimpleNamespace

from rules.models import Rule
from ui.rules_window import (
    RuleManagerDialog,
    _configure_rule_table,
    _select_default_direction,
)


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
