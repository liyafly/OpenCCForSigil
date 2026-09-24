"""Qt rule manager, sandbox, and read-only dictionary inspector."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from rules.conflicts import find_conflicts
from rules.engine import convert_with_overlay
from rules.models import Rule, RuleSnapshot
from rules.precedence import base_direction
from rules.validators import RuleValidationError, validate_rules
from opencc_backend.configs import base_config_options
from rules.store import RuleSet, RuleStore
from rules.importers import ImportResult, reassign_colliding_ids, rule_dedup_key
from ui.i18n import (
    CatalogView,
    Translator,
    configuration_label,
    plugin_window_title,
    rule_validation_message,
    show_error_details,
)
from ui.qt import ask_confirmation, ensure_application, exec_dialog, load_qt
from ui.window_state import restore_window_size, save_window_size


@dataclass(frozen=True)
class RuleImportReview:
    additions: tuple[Rule, ...]
    duplicate_count: int
    diagnostics: tuple[object, ...]
    conflicts: tuple[object, ...]
    id_reassigned_count: int = 0


@dataclass(frozen=True)
class RuleWindowResult:
    selected_id: str
    rulesets: tuple[RuleSet, ...]
    renamed: tuple[tuple[str, str], ...] = ()


def _guarded_rule_dialog(qt_widgets, guard):
    base_dialog = qt_widgets.QDialog

    class GuardedRuleDialog(base_dialog):
        def reject(self):
            if guard():
                super().reject()

    return GuardedRuleDialog()


def review_import(
    existing: Iterable[Rule], imported: ImportResult, *, id_reassigned_count: int = 0
) -> RuleImportReview:
    """Prepare additions without changing the current rule list."""

    existing_rules = tuple(existing)
    known = {rule_dedup_key(rule) for rule in existing_rules}
    additions = []
    duplicates = len(imported.duplicates)
    for rule in imported.rules:
        key = rule_dedup_key(rule)
        if key in known:
            duplicates += 1
        else:
            known.add(key)
            additions.append(rule)
    conflicts = tuple(find_conflicts((*existing_rules, *additions)))
    return RuleImportReview(
        tuple(additions), duplicates, imported.diagnostics, conflicts, id_reassigned_count
    )



def _labels(translator: Any) -> CatalogView:
    return CatalogView(translator or Translator("en"), "rules")





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
    storage_errors: Iterable[str] = (),
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
    profile_id: str | None = None,
    book_fingerprint: str | None = None,
    translator: Any = None,
    ui_preferences=None,
    save_ui_preferences=None,
) -> DictionaryInspection:
    """Display read-only independent comparison results and return them."""

    inspection = inspect_dictionary(
        text,
        config=config,
        official_convert=official_convert,
        comparison_configs=comparison_configs,
        snapshot=snapshot,
        profile_id=profile_id,
        book_fingerprint=book_fingerprint,
    )
    qt = load_qt()
    active_translator = translator or Translator("en")
    ensure_application(qt, language=active_translator.language)
    dialog = qt.QDialog()
    labels = _labels(active_translator)
    separator = active_translator.text("common.label_separator")
    dialog.setWindowTitle(plugin_window_title(
        active_translator, labels["inspector_title"]))
    restore_window_size(
        dialog, ui_preferences, "dictionary_inspector_dialog_size", (720, 500))
    layout = qt.QVBoxLayout(dialog)
    view = qt.QPlainTextEdit()
    view.setReadOnly(True)
    lines = [
        f"{labels['input_label']}{separator}{inspection.input}",
        f"{labels['config_label']}{separator}"
        f"{configuration_label(active_translator, inspection.config)}",
    ]
    lines.extend(
        f"{configuration_label(active_translator, name)}{separator}{value}"
        for name, value in inspection.comparisons
    )
    lines.append(f"{labels['final_label']}{separator}{inspection.final}")
    attribution_key = (
        "rules.attribution_opencc" if inspection.attribution.startswith("OpenCC")
        else "rules.attribution_user"
    )
    lines.append(
        f"{labels['attribution_label']}{separator}"
        f"{active_translator.text(attribution_key)}")
    for item in inspection.classifications:
        category = active_translator.text(f"preview.category_value.{item.category}")
        if category == f"preview.category_value.{item.category}":
            category = active_translator.text("rules.category_unknown")
        confidence = active_translator.text(
            f"rules.confidence.{item.attribution_confidence or 'low'}")
        stage = item.comparison_stage or config
        stage_configs = tuple(stage.split("-vs-"))
        stage_label = " / ".join(configuration_label(active_translator, value)
                                 for value in stage_configs)
        lines.append(active_translator.text(
            "rules.classification",
            source=item.source,
            target=item.target,
            category=category,
            confidence=confidence,
            stage=stage_label,
        ))
    if inspection.matched_rules:
        lines.append(active_translator.text(
            "rules.matched_user_rules", rules=", ".join(inspection.matched_rules)))
    view.setPlainText("\n".join(lines))
    layout.addWidget(view)
    close = qt.QPushButton(labels["close"])
    close.clicked.connect(dialog.accept)
    layout.addWidget(close)
    exec_dialog(dialog)
    save_window_size(
        dialog, "dictionary_inspector_dialog_size", save_ui_preferences)
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
    storage_errors: Iterable[str] = (),
    rulesets: Iterable[RuleSet] | None = None,
    ruleset_id: str | None = None,
    rule_store: RuleStore | None = None,
    jieba_pending: bool = False,
    ui_preferences=None,
    save_ui_preferences=None,
) -> tuple[Rule, ...] | RuleWindowResult | None:
    """Open the manager and return committed rules, or ``None`` on cancel."""

    qt = load_qt()
    active_translator = translator or Translator("en")
    ensure_application(qt, language=active_translator.language)
    dialog = RuleManagerDialog(
        qt,
        tuple(rules),
        translator=active_translator,
        official_convert=official_convert,
        config=config,
        profile_id=profile_id,
        book_fingerprint=book_fingerprint,
        available_configs=available_configs,
        comparison_configs=comparison_configs,
        storage_errors=storage_errors,
        rulesets=rulesets,
        ruleset_id=ruleset_id,
        rule_store=rule_store,
        jieba_pending=jieba_pending,
        ui_preferences=ui_preferences,
        save_ui_preferences=save_ui_preferences,
    )
    exec_dialog(dialog.dialog)
    save_window_size(dialog.dialog, "rules_dialog_size", save_ui_preferences)
    if not dialog.accepted:
        return None
    if dialog._managed:
        return dialog.result
    return tuple(dialog.rules)


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
        storage_errors: Iterable[str] = (),
        rulesets: Iterable[RuleSet] | None = None,
        ruleset_id: str | None = None,
        rule_store: RuleStore | None = None,
        jieba_pending: bool = False,
        ui_preferences=None,
        save_ui_preferences=None,
    ) -> None:
        self._qt = qt_widgets
        self._translator = translator or Translator("en")
        self._labels = _labels(self._translator)
        self._managed = rulesets is not None
        values = tuple(rulesets or (RuleSet(ruleset_id or "default", tuple(rules)),))
        if not values:
            values = (RuleSet(ruleset_id or "default", tuple(rules)),)
        self._rulesets = {item.id: item for item in values}
        self._rule_store = rule_store
        selected = ruleset_id if ruleset_id in self._rulesets else values[0].id
        self._ruleset_id = selected
        self._renamed: list[tuple[str, str]] = []
        self.rules = list(self._rulesets[selected].rules)
        self._initial_ruleset_snapshot = self._ruleset_snapshot()
        self.result: RuleWindowResult | None = None
        self._official_convert = official_convert
        self._config = config
        self._profile_id = profile_id
        self._book_fingerprint = book_fingerprint
        self._available_configs = base_config_options(available_configs)
        self._comparison_configs = tuple(comparison_configs)
        self._storage_errors = tuple(storage_errors)
        self._jieba_pending = bool(jieba_pending)
        self._ui_preferences = dict(ui_preferences or {})
        self._save_ui_preferences_callback = save_ui_preferences
        self._save_ui_preferences = self._store_ui_preferences
        self.accepted = False
        self.dialog = _guarded_rule_dialog(qt_widgets, self._guard_reject)
        self.dialog.setWindowTitle(
            plugin_window_title(self._translator, self._labels["title"]))
        restore_window_size(
            self.dialog, self._ui_preferences, "rules_dialog_size", (840, 540))
        self._build()
        self._populate_rulesets()
        self._refresh()

    def _store_ui_preferences(self, values) -> None:
        self._ui_preferences.update(values)
        if callable(self._save_ui_preferences_callback):
            self._save_ui_preferences_callback(values)

    def _build(self) -> None:
        qt = self._qt
        layout = qt.QVBoxLayout(self.dialog)
        self.jieba_notice = None
        if self._jieba_pending:
            self.jieba_notice = qt.QLabel(self._translator.text("config.jieba_checking"))
            self.jieba_notice.setWordWrap(True)
            layout.addWidget(self.jieba_notice)
        if self._storage_errors:
            notice = qt.QLabel(self._labels["skipped_files"].format(
                files=", ".join(self._storage_errors)))
            notice.setWordWrap(True)
            layout.addWidget(notice)

        ruleset_row = qt.QHBoxLayout()
        ruleset_row.addWidget(qt.QLabel(self._labels["ruleset"]))
        self.ruleset_combo = qt.QComboBox()
        self.new_ruleset_button = qt.QPushButton(self._labels["new_set"])
        self.rename_ruleset_button = qt.QPushButton(self._labels["rename_ruleset"])
        for button in (self.new_ruleset_button, self.rename_ruleset_button):
            button.setAutoDefault(False)
        ruleset_row.addWidget(self.ruleset_combo, 1)
        ruleset_row.addWidget(self.new_ruleset_button)
        ruleset_row.addWidget(self.rename_ruleset_button)
        layout.addLayout(ruleset_row)

        self.table = qt.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            [
                self._labels[key]
                for key in ("type", "direction", "source", "target", "scope", "priority")
            ]
        )
        self.table.setAccessibleName(self._translator.text("a11y.rules.table"))
        _configure_rule_table(self.table, qt)
        layout.addWidget(self.table)
        self.conflict_list = qt.QListWidget()
        self.conflicts_label = qt.QLabel(self._labels["conflicts_title"])
        layout.addWidget(self.conflicts_label)
        self.conflict_list.setMaximumHeight(120)
        self.conflict_list.itemClicked.connect(self._select_conflict_item)
        layout.addWidget(self.conflict_list)
        form = qt.QGridLayout()
        self.type_combo = qt.QComboBox()
        self.type_combo.addItem(self._labels["exact"], "exact")
        self.type_combo.addItem(self._labels["protect"], "protect")
        self.direction_combo = qt.QComboBox()
        for direction in (*self._available_configs, "*"):
            label = (
                self._labels["direction_any"]
                if direction == "*"
                else configuration_label(self._translator, direction)
            )
            self.direction_combo.addItem(label, direction)
        self.source_edit = qt.QLineEdit()
        self.target_edit = qt.QLineEdit()
        self.scope_combo = qt.QComboBox()
        for scope in ("global", "profile", "book"):
            self.scope_combo.addItem(self._labels[f"scope_{scope}"], scope)
        self._set_book_scope_enabled()
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
            label = qt.QLabel(self._labels[key])
            label.setBuddy(widget)
            form.addWidget(label, row // 3, (row % 3) * 2)
            form.addWidget(widget, row // 3, (row % 3) * 2 + 1)
        self.editor_form = form
        layout.addLayout(form)
        editor_box = qt.QGroupBox(self._labels["editor_group"])
        buttons = qt.QHBoxLayout(editor_box)
        self.add_button = qt.QPushButton(self._labels["add"])
        self.update_button = qt.QPushButton(self._labels["update"])
        self.remove_button = qt.QPushButton(self._labels["remove"])
        for button in (self.add_button, self.update_button, self.remove_button):
            button.setAutoDefault(False)
        for button in (self.add_button, self.update_button, self.remove_button):
            buttons.addWidget(button)
        layout.addWidget(editor_box)

        transfer_box = qt.QGroupBox(self._labels["transfer_group"])
        transfer = qt.QHBoxLayout(transfer_box)
        self.import_button = qt.QPushButton(self._labels["import"])
        self.export_button = qt.QPushButton(self._labels["export"])
        for button in (self.import_button, self.export_button):
            button.setAutoDefault(False)
        transfer.addWidget(self.import_button)
        transfer.addWidget(self.export_button)
        layout.addWidget(transfer_box)

        test_box = qt.QGroupBox(self._labels["test_group"])
        test_box.setCheckable(True)
        test_box.setChecked(False)
        self.test_box = test_box
        test_layout = qt.QVBoxLayout(test_box)
        test_buttons = qt.QHBoxLayout()
        self.test_button = qt.QPushButton(self._labels["test"])
        self.inspect_button = qt.QPushButton(self._labels["inspect"])
        for button in (self.test_button, self.inspect_button):
            button.setAutoDefault(False)
        test_buttons.addWidget(self.test_button)
        test_buttons.addWidget(self.inspect_button)
        test_layout.addLayout(test_buttons)
        self.test_input = qt.QPlainTextEdit()
        self.test_input.setPlaceholderText(self._labels["input"])
        test_layout.addWidget(self.test_input)
        self.test_output = qt.QPlainTextEdit()
        self.test_output.setReadOnly(True)
        self.test_output.setPlaceholderText(self._labels["output"])
        test_layout.addWidget(self.test_output)
        layout.addWidget(test_box, 1)

        actions = qt.QHBoxLayout()
        actions.addStretch(1)
        self.apply_button = qt.QPushButton(self._labels["apply"])
        self.cancel_button = qt.QPushButton(self._labels["cancel"])
        for button in (self.apply_button, self.cancel_button):
            button.setAutoDefault(False)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.apply_button)
        layout.addLayout(actions)

        self.ruleset_combo.currentIndexChanged.connect(self._ruleset_changed)
        self.new_ruleset_button.clicked.connect(self._new_ruleset)
        self.rename_ruleset_button.clicked.connect(self._rename_ruleset)
        self.add_button.clicked.connect(self._add)
        self.update_button.clicked.connect(self._update_selected)
        self.remove_button.clicked.connect(self._remove)
        self.test_button.clicked.connect(self._test)
        self.inspect_button.clicked.connect(self._inspect)
        self.import_button.clicked.connect(self._import)
        self.export_button.clicked.connect(self._export)
        self.apply_button.clicked.connect(self._apply)
        self.cancel_button.clicked.connect(self.dialog.reject)
        self.source_edit.returnPressed.connect(self._submit_editor)
        self.target_edit.returnPressed.connect(self._submit_editor)
        self.type_combo.currentIndexChanged.connect(self._type_changed)
        self.table.itemSelectionChanged.connect(self._selection_changed)

    def _populate_rulesets(self) -> None:
        self.ruleset_combo.blockSignals(True)
        self.ruleset_combo.clear()
        for identifier, ruleset in self._rulesets.items():
            label = (
                self._labels["default_set_name"]
                if identifier == "default"
                else ruleset.name or identifier
            )
            self.ruleset_combo.addItem(label, identifier)
        index = self.ruleset_combo.findData(self._ruleset_id)
        if index >= 0:
            self.ruleset_combo.setCurrentIndex(index)
        self.ruleset_combo.blockSignals(False)

    def _stash_ruleset(self) -> None:
        if self._ruleset_id in self._rulesets:
            current = self._rulesets[self._ruleset_id]
            self._rulesets[self._ruleset_id] = RuleSet(
                current.id, tuple(self.rules), current.name)

    def _ruleset_snapshot(self):
        self._stash_ruleset()
        return tuple(
            (identifier, ruleset.name, tuple(ruleset.rules))
            for identifier, ruleset in sorted(self._rulesets.items())
        )

    def _guard_reject(self) -> bool:
        if self._ruleset_snapshot() == self._initial_ruleset_snapshot:
            return True
        return self._confirm_discard_rules()

    def _confirm_discard_rules(self) -> bool:
        message_box = getattr(self._qt, "QMessageBox", None)
        if not callable(message_box):
            return False
        box = message_box(self.dialog)
        box.setWindowTitle(plugin_window_title(
            self._translator, self._translator.text("rules.discard_title")))
        box.setText(self._translator.text("rules.discard_message"))
        discard = box.addButton(
            self._translator.text("rules.discard_confirm"), message_box.AcceptRole)
        back = box.addButton(
            self._translator.text("rules.discard_back"), message_box.RejectRole)
        box.setDefaultButton(back)
        box.setEscapeButton(back)
        exec_dialog(box)
        return box.clickedButton() is discard

    def _ruleset_changed(self, *_args) -> None:
        identifier = self.ruleset_combo.currentData()
        if not identifier or identifier == self._ruleset_id:
            return
        self._stash_ruleset()
        if identifier not in self._rulesets:
            return
        self._ruleset_id = str(identifier)
        self.rules = list(self._rulesets[self._ruleset_id].rules)
        self._refresh()

    def _new_ruleset(self) -> None:
        translator = getattr(self, "_translator", None) or Translator("en")
        identifier, accepted = self._qt.QInputDialog.getText(
            self.dialog, plugin_window_title(translator, self._labels["title"]),
            self._labels["ruleset"])
        identifier = str(identifier).strip()
        if not accepted:
            return
        try:
            _validate_ruleset_id(identifier)
        except ValueError:
            self._warn(self._labels["invalid_ruleset"])
            return
        if identifier in self._rulesets:
            self._warn(self._labels["duplicate_ruleset"])
            return
        self._stash_ruleset()
        self._rulesets[identifier] = RuleSet(identifier)
        self._ruleset_id = identifier
        self.rules = []
        self._populate_rulesets()
        self._refresh()

    def _rename_ruleset(self) -> None:
        old = self._ruleset_id
        translator = getattr(self, "_translator", None) or Translator("en")
        identifier, accepted = self._qt.QInputDialog.getText(
            self.dialog, plugin_window_title(translator, self._labels["title"]),
            self._labels["ruleset"],
            text=old)
        identifier = str(identifier).strip()
        if not accepted or identifier == old:
            return
        try:
            _validate_ruleset_id(identifier)
        except ValueError:
            self._warn(self._labels["invalid_ruleset"])
            return
        if identifier in self._rulesets:
            self._warn(self._labels["duplicate_ruleset"])
            return
        self._stash_ruleset()
        ruleset = self._rulesets.pop(old)
        self._rulesets[identifier] = RuleSet(identifier, ruleset.rules, ruleset.name)
        previous = next((index for index, pair in enumerate(self._renamed)
                         if pair[1] == old), None)
        if previous is None:
            self._renamed.append((old, identifier))
        else:
            original, _current = self._renamed[previous]
            self._renamed[previous] = (original, identifier)
        self._ruleset_id = identifier
        self.rules = list(ruleset.rules)
        self._populate_rulesets()
        self._refresh()

    def _set_book_scope_enabled(self) -> None:
        index = self.scope_combo.findData("book")
        if index < 0:
            return
        model = self.scope_combo.model()
        item = model.item(index) if model is not None else None
        if item is not None:
            item.setEnabled(bool(self._book_fingerprint))

    def _warn(self, message: str) -> None:
        self._qt.QMessageBox.warning(
            self.dialog, plugin_window_title(self._translator, self._labels["title"]), message)

    def _refresh(self) -> None:
        self.table.setRowCount(0)
        for rule in self.rules:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = (
                self._labels.get(rule.type, rule.type),
                (
                    self._labels["direction_any"]
                    if rule.direction == "*"
                    else configuration_label(self._translator, rule.direction)
                ),
                rule.source,
                rule.target or rule.source,
                self._labels.get(f"scope_{rule.scope}", rule.scope),
                str(rule.priority),
            )
            for column, value in enumerate(values):
                self.table.setItem(row, column, self._qt.QTableWidgetItem(value))
        conflicts = find_conflicts(self.rules)
        self.apply_button.setEnabled(not any(conflict.blocking for conflict in conflicts))
        self.conflict_list.clear()
        translator = getattr(self, "_translator", Translator("en"))
        for conflict in conflicts:
            item = self._qt.QListWidgetItem(_conflict_summary(conflict, translator))
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

    def _submit_editor(self) -> None:
        if self.update_button.isEnabled():
            self._update_selected()
        else:
            self._add()

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
            show_error_details(
                self._qt, self.dialog, self._labels["title"],
                rule_validation_message(self._translator, exc), str(exc),
            )
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
            self.test_output.setPlainText(self._labels["no_converter"])
            return
        try:
            result = convert_with_overlay(
                self.test_input.toPlainText(),
                lambda value: convert_for(self._config, value, self._official_convert),
                config=self._config,
                snapshot=RuleSnapshot.freeze(self.rules),
                profile_id=self._profile_id,
                book_fingerprint=self._book_fingerprint,
            )
            lines = [
                        f"{self._labels['original_label']}: {result.original}",
                        f"{self._labels['pre_rules_label']}: {result.after_pre_rules}",
                        f"{self._labels['opencc_label']}: {result.after_opencc}",
                        f"{self._labels['post_rules_label']}: {result.after_post_rules}",
                        f"{self._labels['final_label']}: {result.final}",
                        f"{self._labels['hits_label']}: {len(result.rule_hits)}",
            ]
            lines.extend(self._labels["rule_hit"].format(
                id=hit.rule_id, source=hit.source, target=hit.target,
                start=hit.start, end=hit.end) for hit in result.rule_hits)
            if not result.rule_hits:
                lines.append(self._labels["no_hits"])
            self.test_output.setPlainText("\n".join(lines))
        except Exception as exc:
            show_error_details(
                self._qt, self.dialog, self._labels["title"],
                self._labels["operation_failed"], str(exc),
            )

    def _inspect(self) -> None:
        if self._official_convert is None:
            self.test_output.setPlainText(self._labels["no_converter"])
            return
        text = self.test_input.toPlainText()
        if not text:
            row = self.table.currentRow()
            if 0 <= row < len(self.rules):
                text = self.rules[row].source
        if not text:
            self.test_output.setPlainText(self._labels["input_required"])
            return
        try:
            show_dictionary_inspector(
                text,
                config=self._config,
                official_convert=self._official_convert,
                comparison_configs=self._comparison_configs,
                snapshot=RuleSnapshot.freeze(self.rules),
                profile_id=self._profile_id,
                book_fingerprint=self._book_fingerprint,
                translator=self._translator,
                ui_preferences=self._ui_preferences,
                save_ui_preferences=self._save_ui_preferences,
            )
        except Exception as exc:
            show_error_details(
                self._qt, self.dialog, self._labels["title"],
                self._labels["operation_failed"], str(exc),
            )

    def _import(self) -> None:
        from rules.importers import import_rules

        path, _ = self._qt.QFileDialog.getOpenFileName(
            self.dialog,
            plugin_window_title(self._translator, self._labels["import"]),
            "",
            self._translator.text("rules.import_filter"),
        )
        if not path:
            return
        try:
            options = self._import_options(path)
            if options is None:
                return
            result = import_rules(
                path,
                format=options["format"],
                direction=options["direction"],
                scope=options["scope"],
                profile_id=self._profile_id or "",
                book_fingerprint=self._book_fingerprint or "",
                strict=options["strict"],
            )
            self._stash_ruleset()
            existing_ids = {
                rule.id
                for ruleset in self._rulesets.values()
                for rule in ruleset.rules
            }
            if self._rule_store is not None:
                saved_rulesets, _errors = self._rule_store.list()
                existing_ids.update(
                    rule.id for ruleset in saved_rulesets for rule in ruleset.rules
                )
            reassigned_rules = reassign_colliding_ids(result.rules, existing_ids)
            id_reassigned_count = sum(
                before.id != after.id for before, after in zip(result.rules, reassigned_rules)
            )
            result = replace(result, rules=reassigned_rules)
            review = review_import(
                self.rules, result, id_reassigned_count=id_reassigned_count
            )
            if self._confirm_import(review):
                self.rules.extend(review.additions)
                self._refresh()
        except Exception as exc:
            self._show_exception(exc)

    def _import_options(self, path):
        qt = self._qt
        dialog = qt.QDialog(self.dialog)
        dialog.setWindowTitle(
            plugin_window_title(self._translator, self._labels["import"]))
        restore_window_size(
            dialog, self._ui_preferences, "rules_import_options_dialog_size", (520, 280))
        layout = qt.QVBoxLayout(dialog)
        form = qt.QFormLayout()
        format_combo = qt.QComboBox()
        formats = (("json", "JSON"), ("tsv", "TSV"), ("csv", "CSV"), ("txt", "OpenCC TXT"))
        for value, label in formats:
            format_combo.addItem(label, value)
        suffix = str(path).rsplit(".", 1)[-1].lower() if "." in str(path) else "json"
        suffix = "txt" if suffix in {"opencc", "opencc-txt"} else suffix
        format_index = format_combo.findData(suffix)
        if format_index >= 0:
            format_combo.setCurrentIndex(format_index)
        direction_combo = qt.QComboBox()
        for direction in self._available_configs:
            direction_combo.addItem(direction, direction)
        _select_default_direction(direction_combo, self._config)
        scope_combo = qt.QComboBox()
        for scope in ("global", "profile", "book"):
            scope_combo.addItem(self._labels[f"scope_{scope}"], scope)
        if not self._book_fingerprint:
            index = scope_combo.findData("book")
            model = scope_combo.model()
            item = model.item(index) if model is not None and index >= 0 else None
            if item is not None:
                item.setEnabled(False)
        skip_invalid = qt.QCheckBox(self._labels["skip_invalid"])
        skip_invalid.setChecked(True)
        form.addRow(self._labels["import_format"], format_combo)
        form.addRow(self._labels["direction"], direction_combo)
        form.addRow(self._labels["scope"], scope_combo)
        form.addRow(skip_invalid)
        layout.addLayout(form)
        buttons = qt.QHBoxLayout()
        cancel = qt.QPushButton(self._labels["import_cancel"])
        accept = qt.QPushButton(self._labels["import_add"])
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(accept)
        layout.addLayout(buttons)
        state = {"accepted": False}
        cancel.clicked.connect(dialog.reject)
        accept.clicked.connect(lambda: (state.update(accepted=True), dialog.accept()))
        exec_dialog(dialog)
        save_window_size(
            dialog, "rules_import_options_dialog_size", self._save_ui_preferences)
        if not state["accepted"]:
            return None
        return {
            "format": str(format_combo.currentData()),
            "direction": str(direction_combo.currentData()),
            "scope": str(scope_combo.currentData()),
            "strict": not skip_invalid.isChecked(),
        }

    def _confirm_import(self, review: RuleImportReview) -> bool:
        diagnostics = tuple(review.diagnostics)
        errors = sum(getattr(item, "severity", "") == "error" for item in diagnostics)
        discarded = len(diagnostics) - errors
        message = self._labels["import_summary"].format(
            new=len(review.additions), duplicates=review.duplicate_count,
            discarded=discarded, errors=errors,
        )
        if review.id_reassigned_count:
            message += "\n" + self._translator.text(
                "rules.import_ids_reassigned", count=review.id_reassigned_count
            )
        detail_lines = [self._labels["import_line"].format(
            line=item.line, message=item.message) for item in diagnostics]
        detail_lines.extend(
            _conflict_summary(conflict, self._translator) for conflict in review.conflicts)
        detail = "\n".join(detail_lines)
        qt = self._qt
        dialog = qt.QDialog(self.dialog)
        dialog.setWindowTitle(
            plugin_window_title(self._translator, self._labels["import"]))
        restore_window_size(
            dialog, self._ui_preferences, "rules_import_review_dialog_size", (640, 460))
        layout = qt.QVBoxLayout(dialog)
        summary = qt.QLabel(message)
        summary.setWordWrap(True)
        layout.addWidget(summary)
        details = qt.QPlainTextEdit()
        details.setReadOnly(True)
        details.setPlainText(detail)
        layout.addWidget(qt.QLabel(self._translator.text("common.error_details")))
        layout.addWidget(details, 1)
        buttons = qt.QHBoxLayout()
        cancel = qt.QPushButton(self._labels["import_cancel"])
        accept = qt.QPushButton(self._labels["import_add"])
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(accept)
        layout.addLayout(buttons)
        state = {"accepted": False}
        cancel.clicked.connect(dialog.reject)
        accept.clicked.connect(lambda: (state.update(accepted=True), dialog.accept()))
        exec_dialog(dialog)
        save_window_size(
            dialog, "rules_import_review_dialog_size", self._save_ui_preferences)
        return bool(state["accepted"])

    def _export(self) -> None:
        from rules.exporters import export_rules, export_warnings

        path, _ = self._qt.QFileDialog.getSaveFileName(
            self.dialog,
            plugin_window_title(self._translator, self._labels["export"]),
            self._translator.text("rules.export_default_filename"),
            self._translator.text("rules.export_filter"),
        )
        if not path:
            return
        suffix = path.rsplit(".", 1)[-1].lower() if "." in path else "json"
        try:
            lossy, skipped_txt = export_warnings(self.rules, format=suffix)
        except Exception as exc:
            self._show_exception(exc)
            return
        warnings = []
        if lossy:
            warnings.append(self._translator.text("rules.export_lossy_warning"))
        if skipped_txt:
            warnings.append(self._translator.text(
                "rules.export_txt_skipped", count=skipped_txt))
        if warnings and not ask_confirmation(
            self._qt,
            self.dialog,
            self._labels["title"],
            "\n".join(warnings),
            self._translator,
        ):
            return
        try:
            export_rules(self.rules, path, format=suffix)
        except Exception as exc:
            self._show_exception(exc)

    def _show_exception(self, error: BaseException) -> None:
        summary = (
            rule_validation_message(self._translator, error)
            if isinstance(error, RuleValidationError)
            else self._labels["operation_failed"]
        )
        show_error_details(
            self._qt, self.dialog, self._labels["title"], summary, str(error))

    def _apply(self) -> None:
        self._stash_ruleset()
        self.accepted = True
        if self._managed:
            self.result = RuleWindowResult(
                self._ruleset_id, tuple(self._rulesets.values()), tuple(self._renamed))
        self.dialog.accept()


def _validate_ruleset_id(identifier: str) -> None:
    if (not identifier or identifier in {".", ".."}
            or any(char in identifier for char in ("/", "\\", ":", "\x00"))):
        raise ValueError("ruleset id must be a simple filename-safe identifier")


def _conflict_summary(conflict, translator: Translator) -> str:
    key = f"rules.conflict.{conflict.kind}"
    text = translator.text(key, source=conflict.source)
    if text == key:
        return translator.text(
            "rules.conflict.unknown", kind=conflict.kind, source=conflict.source)
    return text


def _configure_rule_table(table, qt):
    table.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(qt.QAbstractItemView.SelectRows)


def _select_default_direction(combo, config):
    index = combo.findData(base_direction(config))
    if index >= 0:
        combo.setCurrentIndex(index)


__all__ = [
    "DictionaryInspection",
    "RuleImportReview",
    "RuleManagerDialog",
    "RuleWindowResult",
    "convert_for",
    "inspect_dictionary",
    "review_import",
    "show_dictionary_inspector",
    "show_rules_window",
]
