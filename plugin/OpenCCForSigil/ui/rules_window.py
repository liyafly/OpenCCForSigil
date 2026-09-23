"""Qt rule manager, sandbox, and read-only dictionary inspector."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping

from rules.conflicts import find_conflicts
from rules.engine import convert_with_overlay
from rules.models import Rule, RuleSnapshot
from rules.precedence import base_direction
from rules.validators import RuleValidationError, validate_rules
from opencc_backend.configs import V1_CONFIGS


_LABELS = {
    "en": {
        "title": "Rules",
        "add": "Add",
        "update": "Update selected",
        "remove": "Remove",
        "test": "Test",
        "inspect": "Inspect dictionary",
        "inspector_title": "Dictionary Inspector",
        "close": "Close",
        "input_label": "Input",
        "config_label": "Config",
        "final_label": "Final",
        "attribution_label": "Attribution",
        "original_label": "Original",
        "pre_rules_label": "After user pre-rules",
        "opencc_label": "After OpenCC",
        "post_rules_label": "After post-rules",
        "hits_label": "Hits",
        "import": "Import",
        "export": "Export",
        "apply": "Save",
        "cancel": "Cancel",
        "input": "Test text",
        "output": "Sandbox output",
        "direction": "Direction",
        "source": "Source",
        "target": "Target",
        "type": "Type",
        "scope": "Scope",
        "priority": "Priority",
        "exact": "exact",
        "protect": "protect",
    },
    "zh-Hans": {
        "title": "规则管理",
        "add": "新增",
        "update": "更新所选",
        "remove": "删除",
        "test": "测试",
        "inspect": "词典检查",
        "inspector_title": "词典检查",
        "close": "关闭",
        "input_label": "输入",
        "config_label": "配置",
        "final_label": "最终结果",
        "attribution_label": "归因",
        "original_label": "原文",
        "pre_rules_label": "用户预规则后",
        "opencc_label": "OpenCC 后",
        "post_rules_label": "后置规则后",
        "hits_label": "命中",
        "import": "导入",
        "export": "导出",
        "apply": "保存",
        "cancel": "取消",
        "input": "测试文本",
        "output": "沙箱输出",
        "direction": "方向",
        "source": "源文本",
        "target": "目标文本",
        "type": "类型",
        "scope": "范围",
        "priority": "优先级",
        "exact": "精确",
        "protect": "保护",
    },
    "zh-Hant": {
        "title": "規則管理",
        "add": "新增",
        "update": "更新所選",
        "remove": "刪除",
        "test": "測試",
        "inspect": "詞典檢查",
        "inspector_title": "詞典檢查",
        "close": "關閉",
        "input_label": "輸入",
        "config_label": "設定",
        "final_label": "最終結果",
        "attribution_label": "歸因",
        "original_label": "原文",
        "pre_rules_label": "使用者預規則後",
        "opencc_label": "OpenCC 後",
        "post_rules_label": "後置規則後",
        "hits_label": "命中",
        "import": "匯入",
        "export": "匯出",
        "apply": "儲存",
        "cancel": "取消",
        "input": "測試文字",
        "output": "沙箱輸出",
        "direction": "方向",
        "source": "來源文字",
        "target": "目標文字",
        "type": "類型",
        "scope": "範圍",
        "priority": "優先級",
        "exact": "精確",
        "protect": "保護",
    },
}

STANDARD_CONFIGS = V1_CONFIGS


def _labels(translator: Any) -> Mapping[str, str]:
    language = getattr(translator, "language", "en") if translator is not None else "en"
    return _LABELS.get(language, _LABELS["en"])


@dataclass(frozen=True)
class DictionaryInspection:
    input: str
    config: str
    comparisons: tuple[tuple[str, str], ...]
    final: str
    matched_rules: tuple[str, ...] = ()
    attribution: str = "OpenCC"
    classifications: tuple[object, ...] = ()


def inspect_dictionary(
    text: str,
    *,
    config: str,
    official_convert: Callable[[str], str] | object,
    comparison_configs: Iterable[str] = (),
    snapshot: RuleSnapshot | None = None,
    profile_id: str | None = None,
    book_fingerprint: str | None = None,
) -> DictionaryInspection:
    """Run independent comparison callbacks on the same original input."""

    comparisons = tuple(
        (name, _require_text(convert_for(name, text, official_convert)))
        for name in comparison_configs
    )
    if snapshot is None:
        snapshot = RuleSnapshot.freeze(())
    result = convert_with_overlay(
        text,
        lambda value: convert_for(config, value, official_convert),
        config=config,
        snapshot=snapshot,
        profile_id=profile_id,
        book_fingerprint=book_fingerprint,
    )
    from core.classifier import classify_conversion
    classification = classify_conversion(
        text, config, lambda name, value: convert_for(name, value, official_convert))
    return DictionaryInspection(
        text,
        config,
        comparisons,
        result.final,
        tuple(hit.rule_id for hit in result.rule_hits),
        f"OpenCC:{config}/comparative_config_diff",
        classification.changes,
    )


def show_dictionary_inspector(
    text: str,
    *,
    config: str,
    official_convert: Callable[[str], str] | object,
    comparison_configs: Iterable[str] = (),
    snapshot: RuleSnapshot | None = None,
    translator: Any = None,
) -> DictionaryInspection:
    """Display read-only independent comparison results and return them."""

    inspection = inspect_dictionary(
        text,
        config=config,
        official_convert=official_convert,
        comparison_configs=comparison_configs,
        snapshot=snapshot,
    )
    qt = _load_qt_widgets()
    _ensure_application(qt)
    dialog = qt.QDialog()
    labels = _labels(translator)
    dialog.setWindowTitle(labels["inspector_title"])
    layout = qt.QVBoxLayout(dialog)
    view = qt.QPlainTextEdit()
    view.setReadOnly(True)
    lines = [
        f"{labels['input_label']}: {inspection.input}",
        f"{labels['config_label']}: {inspection.config}",
    ]
    lines.extend(f"{name}: {value}" for name, value in inspection.comparisons)
    lines.append(f"{labels['final_label']}: {inspection.final}")
    lines.append(f"{labels['attribution_label']}: {inspection.attribution}")
    lines.extend(f"{item.source!r} → {item.target!r}: {item.category} "
                 f"({item.attribution_confidence}; {item.comparison_stage or config})"
                 for item in inspection.classifications)
    if inspection.matched_rules:
        lines.append("UserRule: " + ", ".join(inspection.matched_rules))
    view.setPlainText("\n".join(lines))
    layout.addWidget(view)
    close = qt.QPushButton(labels["close"])
    close.clicked.connect(dialog.accept)
    layout.addWidget(close)
    exec_method = getattr(dialog, "exec", None) or dialog.exec_
    exec_method()
    return inspection


def convert_for(config: str, text: str, backend: Any) -> str:
    """Invoke a supplied callback/backend without importing OpenCC."""

    method = getattr(backend, "convert_for_config", None)
    if callable(method):
        return method(config, text)
    method = getattr(backend, "convert", None)
    if callable(method):
        if getattr(backend, "config", None) != config:
            raise TypeError("comparison requires a config-aware backend")
        return method(text)
    if callable(backend):
        # Comparison callbacks must accept the selected config explicitly;
        # silently retrying with one argument can show the wrong config.
        return backend(config, text)
    raise TypeError("official_convert must be callable or provide convert/convert_for_config")


def _require_text(value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError(f"official conversion callback must return str, got {type(value).__name__}")
    return value


def show_rules_window(
    rules: Iterable[Rule],
    *,
    translator: Any = None,
    official_convert: Callable[[str], str] | object | None = None,
    config: str = "s2t",
    profile_id: str | None = None,
    book_fingerprint: str | None = None,
    available_configs: Iterable[str] | None = None,
    comparison_configs: Iterable[str] = (),
) -> tuple[Rule, ...] | None:
    """Open the manager and return committed rules, or ``None`` on cancel."""

    qt = _load_qt_widgets()
    _ensure_application(qt)
    dialog = RuleManagerDialog(
        qt,
        tuple(rules),
        translator=translator,
        official_convert=official_convert,
        config=config,
        profile_id=profile_id,
        book_fingerprint=book_fingerprint,
        available_configs=available_configs,
        comparison_configs=comparison_configs,
    )
    exec_method = getattr(dialog.dialog, "exec", None) or dialog.dialog.exec_
    exec_method()
    return tuple(dialog.rules) if dialog.accepted else None


class RuleManagerDialog:
    def __init__(
        self,
        qt_widgets: Any,
        rules: tuple[Rule, ...],
        *,
        translator: Any = None,
        official_convert: Any = None,
        config: str = "s2t",
        profile_id: str | None = None,
        book_fingerprint: str | None = None,
        available_configs: Iterable[str] | None = None,
        comparison_configs: Iterable[str] = (),
    ) -> None:
        self._qt = qt_widgets
        self._translator = translator
        self._labels = _labels(translator)
        self.rules = list(rules)
        self._official_convert = official_convert
        self._config = config
        self._profile_id = profile_id
        self._book_fingerprint = book_fingerprint
        self._available_configs = _base_config_options(available_configs)
        self._comparison_configs = tuple(comparison_configs)
        self.accepted = False
        self.dialog = qt_widgets.QDialog()
        self.dialog.setWindowTitle(self._labels["title"])
        self.dialog.resize(840, 540)
        self._build()
        self._refresh()

    def _build(self) -> None:
        qt = self._qt
        layout = qt.QVBoxLayout(self.dialog)
        self.table = qt.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            [
                self._labels[key]
                for key in ("type", "direction", "source", "target", "scope", "priority")
            ]
        )
        _configure_rule_table(self.table, qt)
        layout.addWidget(self.table)
        self.conflict_list = qt.QListWidget()
        self.conflict_list.itemClicked.connect(self._select_conflict_item)
        layout.addWidget(self.conflict_list)
        form = qt.QGridLayout()
        self.type_combo = qt.QComboBox()
        self.type_combo.addItem(self._labels["exact"], "exact")
        self.type_combo.addItem(self._labels["protect"], "protect")
        self.direction_combo = qt.QComboBox()
        for direction in (*self._available_configs, "*"):
            self.direction_combo.addItem(direction, direction)
        self.source_edit = qt.QLineEdit()
        self.target_edit = qt.QLineEdit()
        self.scope_combo = qt.QComboBox()
        for scope in ("global", "profile", "book"):
            self.scope_combo.addItem(scope, scope)
        self.priority_edit = qt.QSpinBox()
        self.priority_edit.setRange(-100000, 100000)
        self.priority_edit.setValue(100)
        _select_default_direction(self.direction_combo, self._config)
        controls = (
            ("type", self.type_combo),
            ("direction", self.direction_combo),
            ("source", self.source_edit),
            ("target", self.target_edit),
            ("scope", self.scope_combo),
            ("priority", self.priority_edit),
        )
        for row, (key, widget) in enumerate(controls):
            form.addWidget(qt.QLabel(self._labels[key]), row // 3, (row % 3) * 2)
            form.addWidget(widget, row // 3, (row % 3) * 2 + 1)
        layout.addLayout(form)
        buttons = qt.QHBoxLayout()
        self.add_button = qt.QPushButton(self._labels["add"])
        self.update_button = qt.QPushButton(self._labels["update"])
        self.remove_button = qt.QPushButton(self._labels["remove"])
        self.test_button = qt.QPushButton(self._labels["test"])
        self.inspect_button = qt.QPushButton(self._labels["inspect"])
        self.import_button = qt.QPushButton(self._labels["import"])
        self.export_button = qt.QPushButton(self._labels["export"])
        self.apply_button = qt.QPushButton(self._labels["apply"])
        self.cancel_button = qt.QPushButton(self._labels["cancel"])
        for button in (
            self.add_button,
            self.update_button,
            self.remove_button,
            self.test_button,
            self.inspect_button,
            self.import_button,
            self.export_button,
            self.apply_button,
            self.cancel_button,
        ):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.test_input = qt.QLineEdit()
        self.test_input.setPlaceholderText(self._labels["input"])
        layout.addWidget(self.test_input)
        self.test_output = qt.QPlainTextEdit()
        self.test_output.setReadOnly(True)
        self.test_output.setPlaceholderText(self._labels["output"])
        layout.addWidget(self.test_output)
        self.add_button.clicked.connect(self._add)
        self.update_button.clicked.connect(self._update_selected)
        self.remove_button.clicked.connect(self._remove)
        self.test_button.clicked.connect(self._test)
        self.inspect_button.clicked.connect(self._inspect)
        self.import_button.clicked.connect(self._import)
        self.export_button.clicked.connect(self._export)
        self.apply_button.clicked.connect(self._apply)
        self.cancel_button.clicked.connect(self.dialog.reject)
        self.type_combo.currentIndexChanged.connect(self._type_changed)
        self.table.itemSelectionChanged.connect(self._selection_changed)

    def _refresh(self) -> None:
        self.table.setRowCount(0)
        for rule in self.rules:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = (
                rule.type,
                rule.direction,
                rule.source,
                rule.target or rule.source,
                rule.scope,
                str(rule.priority),
            )
            for column, value in enumerate(values):
                self.table.setItem(row, column, self._qt.QTableWidgetItem(value))
        conflicts = find_conflicts(self.rules)
        self.apply_button.setEnabled(not any(conflict.blocking for conflict in conflicts))
        self.conflict_list.clear()
        for conflict in conflicts:
            item = self._qt.QListWidgetItem(conflict.message)
            item.setData(getattr(self._qt.Qt, "UserRole", 32),
                         tuple(rule.id for rule in conflict.rules))
            self.conflict_list.addItem(item)
        self._update_selection_state()

    def _add(self) -> None:
        rule = self._rule_from_form()
        if rule is None:
            return
        self.rules.append(rule)
        self._refresh()

    def _update_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.rules):
            return
        candidate = self._rule_from_form()
        if candidate is None:
            return
        previous = self.rules[row]
        updated_at = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
            "+00:00", "Z")
        self.rules[row] = replace(candidate, id=previous.id,
                                  created_at=previous.created_at, updated_at=updated_at)
        self._refresh()

    def _rule_from_form(self):
        rule_type = str(self.type_combo.currentData())
        values = {
            "type": rule_type,
            "direction": str(self.direction_combo.currentData()),
            "source": self.source_edit.text(),
            "target": self.source_edit.text() if rule_type == "protect" else self.target_edit.text(),
            "scope": str(self.scope_combo.currentData()),
            "priority": int(self.priority_edit.value()),
            "profile_id": self._profile_id or "",
            "book_fingerprint": self._book_fingerprint or "",
        }
        try:
            return validate_rules((Rule.from_dict(values),))[0]
        except RuleValidationError as exc:
            self._qt.QMessageBox.warning(self.dialog, self._labels["title"], str(exc))
            return None

    def _remove(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self.rules):
            self.rules.pop(row)
            self._refresh()

    def _load_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.rules):
            return
        rule = self.rules[row]
        self.type_combo.setCurrentIndex(self.type_combo.findData(rule.type))
        self.direction_combo.setCurrentIndex(self.direction_combo.findData(rule.direction))
        self.source_edit.setText(rule.source)
        self.target_edit.setText(rule.target)
        self.scope_combo.setCurrentIndex(self.scope_combo.findData(rule.scope))
        self.priority_edit.setValue(rule.priority)
        self._type_changed()
        if rule.type == "protect":
            self.target_edit.clear()

    def _type_changed(self, *_args):
        is_protect = self.type_combo.currentData() == "protect"
        self.target_edit.setEnabled(not is_protect)
        if is_protect:
            self.target_edit.clear()

    def _selection_changed(self):
        self._load_selected()
        self._update_selection_state()

    def _update_selection_state(self):
        row = self.table.currentRow()
        self.update_button.setEnabled(0 <= row < len(self.rules))

    def _select_conflict_item(self, item):
        rule_ids = item.data(getattr(self._qt.Qt, "UserRole", 32))
        if not rule_ids:
            return
        row = next((index for index, rule in enumerate(self.rules)
                    if rule.id in rule_ids), -1)
        if row >= 0:
            self.table.selectRow(row)

    def _test(self) -> None:
        if self._official_convert is None:
            self.test_output.setPlainText("No official conversion callback supplied")
            return
        try:
            result = convert_with_overlay(
                self.test_input.text(),
                lambda value: convert_for(self._config, value, self._official_convert),
                config=self._config,
                snapshot=RuleSnapshot.freeze(self.rules),
                profile_id=self._profile_id,
                book_fingerprint=self._book_fingerprint,
            )
            self.test_output.setPlainText(
                "\n".join(
                    (
                        f"{self._labels['original_label']}: {result.original}",
                        f"{self._labels['pre_rules_label']}: {result.after_pre_rules}",
                        f"{self._labels['opencc_label']}: {result.after_opencc}",
                        f"{self._labels['post_rules_label']}: {result.after_post_rules}",
                        f"{self._labels['final_label']}: {result.final}",
                        f"{self._labels['hits_label']}: {len(result.rule_hits)}",
                    )
                )
            )
        except Exception as exc:
            self.test_output.setPlainText(str(exc))

    def _inspect(self) -> None:
        if self._official_convert is None:
            self.test_output.setPlainText("No official conversion callback supplied")
            return
        text = self.test_input.text()
        if not text:
            row = self.table.currentRow()
            if 0 <= row < len(self.rules):
                text = self.rules[row].source
        if not text:
            self.test_output.setPlainText("Enter text for dictionary inspection")
            return
        try:
            show_dictionary_inspector(
                text,
                config=self._config,
                official_convert=self._official_convert,
                comparison_configs=self._comparison_configs,
                snapshot=RuleSnapshot.freeze(self.rules),
                translator=self._translator,
            )
        except Exception as exc:
            self.test_output.setPlainText(str(exc))

    def _import(self) -> None:
        from rules.importers import import_rules

        path, _ = self._qt.QFileDialog.getOpenFileName(
            self.dialog,
            self._labels["import"],
            "",
            "Rules (*.json *.tsv *.csv *.txt);;All files (*)",
        )
        if not path:
            return
        try:
            result = import_rules(path, direction=str(self.direction_combo.currentData()))
            self.rules.extend(result.rules)
            self._refresh()
            if result.conflicts:
                self._qt.QMessageBox.warning(
                    self.dialog,
                    self._labels["title"],
                    "\n".join(conflict.message for conflict in result.conflicts),
                )
        except Exception as exc:
            self._qt.QMessageBox.warning(self.dialog, self._labels["title"], str(exc))

    def _export(self) -> None:
        from rules.exporters import export_rules

        path, _ = self._qt.QFileDialog.getSaveFileName(
            self.dialog,
            self._labels["export"],
            "rules.json",
            "JSON (*.json);;TSV (*.tsv);;CSV (*.csv);;OpenCC TXT (*.txt)",
        )
        if not path:
            return
        suffix = path.rsplit(".", 1)[-1].lower() if "." in path else "json"
        try:
            export_rules(self.rules, path, format=suffix)
        except Exception as exc:
            self._qt.QMessageBox.warning(self.dialog, self._labels["title"], str(exc))

    def _apply(self) -> None:
        self.accepted = True
        self.dialog.accept()


def _load_qt_widgets() -> Any:
    try:
        from PySide6 import QtCore, QtWidgets

        QtWidgets.Qt = QtCore.Qt
        return QtWidgets
    except ImportError:
        try:
            from PyQt5 import QtCore, QtWidgets

            QtWidgets.Qt = QtCore.Qt
            return QtWidgets
        except ImportError as exc:
            raise RuntimeError("Sigil Qt runtime is unavailable") from exc


_application: Any = None


def _ensure_application(qt: Any) -> Any:
    global _application
    app = qt.QApplication.instance()
    if app is None:
        import sys

        app = qt.QApplication(sys.argv)
    _application = app
    return app


def _base_config_options(available_configs: Iterable[str] | None) -> tuple[str, ...]:
    values = STANDARD_CONFIGS if available_configs is None else available_configs
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        direction = base_direction(str(value))
        if direction in STANDARD_CONFIGS and direction not in seen:
            seen.add(direction)
            result.append(direction)
    return tuple(result)


def _configure_rule_table(table, qt):
    table.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(qt.QAbstractItemView.SelectRows)


def _select_default_direction(combo, config):
    index = combo.findData(base_direction(config))
    if index >= 0:
        combo.setCurrentIndex(index)


__all__ = [
    "DictionaryInspection",
    "RuleManagerDialog",
    "STANDARD_CONFIGS",
    "convert_for",
    "inspect_dictionary",
    "show_dictionary_inspector",
    "show_rules_window",
]
