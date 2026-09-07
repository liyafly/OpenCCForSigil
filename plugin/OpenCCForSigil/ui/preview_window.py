"""Minimal Preview UI for the first interactive conversion phase."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Sequence, Tuple

from core.preview import PreviewError, PreviewSession
from core.workflow import PlannedDocument
from opencc_backend.configs import (
    BASE_CONFIG_BY_JIEBA,
    JIEBA_CONFIG_BY_BASE,
    V1_CONFIGS,
)
from sigil.scope import Scope, ScopeSelectionError, TargetSelection, TextFile, resolve_target_selection
from ui.i18n import LANGUAGE_LABELS, SUPPORTED_LANGUAGES, Translator


class UIUnavailableError(RuntimeError):
    """Raised when Sigil's bundled Qt runtime cannot be imported."""


@dataclass(frozen=True)
class PreviewOutcome:
    accepted: bool
    previews: Tuple[PreviewSession, ...]


@dataclass(frozen=True)
class ScopeOutcome:
    accepted: bool
    selection: TargetSelection | None
    language: str


class ProgressReporter:
    """A lightweight progress view driven by workflow file boundaries."""

    def __init__(self, qt_widgets: Any, total: int) -> None:
        self._qt = qt_widgets
        self._cancelled = False
        self.dialog = qt_widgets.QProgressDialog(
            "", _translator.text("common.cancel"), 0, total
        )
        self.dialog.setWindowTitle(_translator.text("progress.title"))
        self.dialog.setAutoClose(False)
        self.dialog.setAutoReset(False)
        self.dialog.canceled.connect(self._mark_cancelled)
        self.dialog.show()

    def _mark_cancelled(self) -> None:
        self._cancelled = True

    def update(self, phase: str, index: int, total: int, href: str) -> None:
        self.dialog.setMaximum(max(total, 1))
        self.dialog.setValue(index)
        self.dialog.setLabelText(
            _translator.text(
                "progress.status",
                phase=_translator.text(f"progress.phase.{phase}"),
                index=index,
                total=total,
                file=href,
            )
        )
        self._qt.QApplication.processEvents()

    def cancelled(self) -> bool:
        self._qt.QApplication.processEvents()
        return self._cancelled

    def close(self) -> None:
        self.dialog.close()


_translator = Translator("en")


def set_ui_language(language: str) -> None:
    """Set the language used by all dialogs in this plugin invocation."""

    _translator.set_language(language)


CONVERSION_LABELS = {
    "s2t": "简体 → 通用繁体 (s2t)",
    "s2tw": "简体 → 台湾繁体字形 (s2tw)",
    "s2twp": "简体 → 台湾繁体 + 台湾词汇 (s2twp)",
    "s2hk": "简体 → 香港繁体字形 (s2hk)",
    "s2hkp": "简体 → 香港繁体 + 香港词汇 (s2hkp)",
    "t2s": "通用繁体 → 简体 (t2s)",
    "tw2s": "台湾繁体 → 简体字形 (tw2s)",
    "tw2sp": "台湾繁体 → 简体 + 词汇 (tw2sp)",
    "hk2s": "香港繁体 → 简体字形 (hk2s)",
    "hk2sp": "香港繁体 → 简体 + 词汇 (hk2sp)",
    "t2tw": "通用繁体 → 台湾繁体 (t2tw)",
    "t2hk": "通用繁体 → 香港繁体 (t2hk)",
    "tw2t": "台湾繁体 → 通用繁体 (tw2t)",
    "hk2t": "香港繁体 → 通用繁体 (hk2t)",
    "t2jp": "繁体 → 日文新字体 (t2jp)",
    "jp2t": "日文新字体 → 通用繁体 (jp2t)",
}
CONFIG_SELECTION_ORDER = tuple(config for config in V1_CONFIGS if config in CONVERSION_LABELS)


def choose_conversion_config(
    available_configs: Sequence[str],
    *,
    default_config: str = "s2t",
) -> str | None:
    """Ask for an explicit conversion direction before building a plan.

    This selector exposes pinned upstream standard configs and, when the
    selected payload proves the official native plugin is present, an advanced
    Jieba checkbox. The selected concrete config is frozen into the plan.
    """

    qt_widgets = _load_qt_widgets()
    available = set(available_configs)
    configs = tuple(config for config in CONFIG_SELECTION_ORDER if config in available)
    if not configs:
        raise UIUnavailableError(_translator.text("error.no_config"))

    _ensure_application(qt_widgets)
    jieba_configs = {
        base: plugin
        for base, plugin in JIEBA_CONFIG_BY_BASE.items()
        if plugin in available
    }
    dialog = _ConversionConfigDialog(
        qt_widgets, configs, default_config, jieba_configs, translator=_translator
    )
    exec_method = getattr(dialog.dialog, "exec", None) or dialog.dialog.exec_
    exec_method()
    return dialog.selected_config if dialog.accepted else None


def choose_scope(adapter: Any, *, initial_language: str = "en") -> ScopeOutcome:
    """Choose a frozen XHTML target set after enumerating metadata only."""

    inventory = tuple(adapter.text_file_inventory())
    selected_ids, ignored_non_xhtml = _selected_xhtml_ids_and_ignored(adapter, inventory)
    language = initial_language or _translator.language
    _translator.set_language(language)
    qt_widgets = _load_qt_widgets()
    _ensure_application(qt_widgets)
    dialog = _ScopeDialog(
        qt_widgets,
        inventory,
        selected_ids,
        language,
        _translator,
        ignored_non_xhtml=ignored_non_xhtml,
    )
    exec_method = getattr(dialog.dialog, "exec", None) or dialog.dialog.exec_
    exec_method()
    if not dialog.accepted:
        return ScopeOutcome(False, None, dialog.language)
    _translator.set_language(dialog.language)
    selection = resolve_target_selection(
        inventory, dialog.scope, dialog.selected_ids()
    )
    return ScopeOutcome(True, selection, dialog.language)


def create_progress_reporter(total: int) -> ProgressReporter:
    """Create a progress reporter using Sigil's already available Qt runtime."""

    qt_widgets = _load_qt_widgets()
    _ensure_application(qt_widgets)
    return ProgressReporter(qt_widgets, total)


def _selected_xhtml_ids(adapter: Any, inventory: Tuple[TextFile, ...]) -> Tuple[str, ...]:
    return _selected_xhtml_ids_and_ignored(adapter, inventory)[0]


def _selected_xhtml_ids_and_ignored(
    adapter: Any,
    inventory: Tuple[TextFile, ...],
) -> Tuple[Tuple[str, ...], int]:
    selected_iter = getattr(adapter, "selected_ids", None)
    if not callable(selected_iter):
        return (), 0
    known_ids = {item.file_id for item in inventory}
    selected = tuple(selected_iter())
    return (
        tuple(file_id for file_id in selected if file_id in known_ids),
        sum(file_id not in known_ids for file_id in selected),
    )


def show_preview(planned: Sequence[PlannedDocument]) -> PreviewOutcome:
    """Show a preview and return the sessions containing user decisions."""

    qt_widgets = _load_qt_widgets()
    previews = tuple(PreviewSession(item.plan) for item in planned)
    _ensure_application(qt_widgets)
    dialog = _PreviewDialog(qt_widgets, planned, previews)
    exec_method = getattr(dialog.dialog, "exec", None) or dialog.dialog.exec_
    exec_method()
    return PreviewOutcome(accepted=dialog.applied, previews=previews)


def show_result(
    *,
    status: str,
    files_scanned: int,
    files_changed: int,
    accepted_changes: int,
    skipped_changes: int,
    failed_file: str | None = None,
) -> None:
    """Show a concise localized terminal result after the write boundary."""

    qt_widgets = _load_qt_widgets()
    _ensure_application(qt_widgets)
    if status == "partial_failure":
        message = _translator.text(
            "result.partial",
            changed=files_changed,
            accepted=accepted_changes,
            failed_file=failed_file or "?",
        )
        method = getattr(qt_widgets.QMessageBox, "warning")
    elif status == "cancelled":
        message = _translator.text("result.cancelled")
        method = getattr(qt_widgets.QMessageBox, "information")
    elif accepted_changes == 0 and skipped_changes:
        message = _translator.text(
            "result.skipped",
            files=files_scanned,
            skipped=skipped_changes,
        )
        method = getattr(qt_widgets.QMessageBox, "information")
    elif accepted_changes == 0:
        message = _translator.text("result.noop", files=files_scanned)
        method = getattr(qt_widgets.QMessageBox, "information")
    else:
        message = _translator.text(
            "result.done",
            changed=files_changed,
            files=files_scanned,
            accepted=accepted_changes,
            skipped=skipped_changes,
        )
        method = getattr(qt_widgets.QMessageBox, "information")
    method(None, _translator.text("app.title"), message)


_application: Any = None


def _ensure_application(qt_widgets: Any) -> Any:
    """Return the one process-level QApplication used by every plugin dialog."""

    global _application
    application = qt_widgets.QApplication.instance()
    if application is None:
        import sys

        application = qt_widgets.QApplication(sys.argv)
    # Keep a strong module-level reference.  Some Qt bindings only retain a
    # weak ownership handle for an application created from Python.
    _application = application
    return application


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
            raise UIUnavailableError(_translator.text("error.ui_unavailable")) from exc


class _PreviewDialog:
    def __init__(self, qt_widgets: Any, planned, previews: Tuple[PreviewSession, ...]) -> None:
        self._qt = qt_widgets
        self._planned = planned
        self._previews = previews
        self._entries: List[Tuple[PreviewSession, str]] = []
        self.applied = False

        self.dialog = qt_widgets.QDialog()
        self.dialog.setWindowTitle(_translator.text("preview.title"))
        self.dialog.resize(900, 620)
        self._build()
        self._refresh()

    def _build(self) -> None:
        qt = self._qt
        layout = qt.QVBoxLayout(self.dialog)

        self.summary = qt.QLabel()
        layout.addWidget(self.summary)

        self.list_widget = qt.QListWidget()
        self.list_widget.currentRowChanged.connect(self._show_current)
        layout.addWidget(self.list_widget)

        self.detail = qt.QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(150)
        layout.addWidget(self.detail)

        buttons = qt.QHBoxLayout()
        self.accept_this_button = qt.QPushButton(_translator.text("preview.accept_this"))
        self.reject_this_button = qt.QPushButton(_translator.text("preview.skip_this"))
        self.accept_file_button = qt.QPushButton(_translator.text("preview.accept_file"))
        self.reject_file_button = qt.QPushButton(_translator.text("preview.skip_file"))
        self.accept_all_button = qt.QPushButton(_translator.text("preview.accept_all"))
        self.reject_all_button = qt.QPushButton(_translator.text("preview.skip_all"))
        self.apply_button = qt.QPushButton(_translator.text("preview.apply"))
        self.cancel_button = qt.QPushButton(_translator.text("common.cancel"))
        for button in (
            self.accept_this_button,
            self.reject_this_button,
            self.accept_file_button,
            self.reject_file_button,
            self.accept_all_button,
            self.reject_all_button,
            self.apply_button,
            self.cancel_button,
        ):
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self.accept_this_button.clicked.connect(self._accept_this)
        self.reject_this_button.clicked.connect(self._reject_this)
        self.accept_file_button.clicked.connect(self._accept_file)
        self.reject_file_button.clicked.connect(self._reject_file)
        self.accept_all_button.clicked.connect(self._accept_all)
        self.reject_all_button.clicked.connect(self._reject_all)
        self.apply_button.clicked.connect(self._apply)
        self.cancel_button.clicked.connect(self.dialog.reject)

    def _refresh(self) -> None:
        self._entries = [
            (preview, change.change_id)
            for preview in self._previews
            for change in preview.changes
        ]
        current_row = self.list_widget.currentRow()
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for preview, change_id in self._entries:
            change = next(item for item in preview.changes if item.change_id == change_id)
            decision = preview.decision(change_id)
            prefix = "?" if decision is None else "✓" if decision.value.startswith("accept") else "×"
            text = f"{prefix} {change.file_id}: {change.source!r} → {change.target!r}"
            self.list_widget.addItem(text)
        self.list_widget.blockSignals(False)

        if self._entries:
            row = current_row if 0 <= current_row < len(self._entries) else 0
            self.list_widget.setCurrentRow(row)
        else:
            self.detail.setPlainText(_translator.text("preview.no_changes"))
        self._update_summary()

    def _update_summary(self) -> None:
        totals = {"total": 0, "accepted": 0, "rejected": 0, "undecided": 0}
        for preview in self._previews:
            for key, value in preview.summary().items():
                totals[key] += value
        self.summary.setText(_translator.text("preview.summary", files=len(self._previews), **totals))
        has_current = bool(self._entries)
        self.accept_this_button.setEnabled(has_current)
        self.reject_this_button.setEnabled(has_current)
        self.accept_file_button.setEnabled(has_current)
        self.reject_file_button.setEnabled(has_current)
        # An explicit repeat of a bulk action is allowed to reverse prior
        # per-item decisions, so both global buttons stay available while the
        # preview contains changes.  Applying remains blocked until every
        # change has a decision, including a preview with no changes.
        has_entries = bool(self._entries)
        self.accept_all_button.setEnabled(has_entries)
        self.reject_all_button.setEnabled(has_entries)
        self.apply_button.setEnabled(totals["undecided"] == 0)

    def _show_current(self, row: int) -> None:
        if row < 0 or row >= len(self._entries):
            self.detail.clear()
            return
        preview, change_id = self._entries[row]
        change = next(item for item in preview.changes if item.change_id == change_id)
        self.detail.setPlainText(
            f"{_translator.text('preview.rule')}: {change.rule_source}\n"
            f"{_translator.text('preview.category')}: {change.category}    "
            f"{_translator.text('preview.risk')}: {change.risk}\n"
            f"{_translator.text('preview.before')}: "
            f"{change.context_before}{change.source}{change.context_after}\n"
            f"{_translator.text('preview.change')}: {change.source!r} → {change.target!r}"
        )

    def _current_entry(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self._entries):
            return None
        return self._entries[row]

    def _accept_this(self) -> None:
        entry = self._current_entry()
        if entry is None:
            return
        entry[0].accept_this(entry[1])
        self._refresh()

    def _reject_this(self) -> None:
        entry = self._current_entry()
        if entry is None:
            return
        entry[0].reject_this(entry[1])
        self._refresh()

    def _accept_file(self) -> None:
        entry = self._current_entry()
        if entry is None:
            return
        entry[0].accept_all(overwrite=True)
        self._refresh()

    def _reject_file(self) -> None:
        entry = self._current_entry()
        if entry is None:
            return
        entry[0].reject_all(overwrite=True)
        self._refresh()

    def _accept_all(self) -> None:
        for preview in self._previews:
            preview.accept_all(overwrite=True)
        self._refresh()

    def _reject_all(self) -> None:
        for preview in self._previews:
            preview.reject_all(overwrite=True)
        self._refresh()

    def _apply(self) -> None:
        if any(preview.undecided() for preview in self._previews):
            self._update_summary()
            return
        try:
            for preview in self._previews:
                preview.finalize()
        except PreviewError:
            self._qt.QMessageBox.warning(self.dialog, _translator.text("preview.title"), _translator.text("preview.incomplete"))
            return
        self.applied = True
        self.dialog.accept()


class _ConversionConfigDialog:
    def __init__(
        self,
        qt_widgets: Any,
        configs: Tuple[str, ...],
        default_config: str,
        jieba_configs: dict[str, str],
        *,
        translator: Translator,
    ) -> None:
        self._qt = qt_widgets
        self._jieba_configs = jieba_configs
        self._translator = translator
        self.accepted = False
        self.selected_config = None
        self.dialog = qt_widgets.QDialog()
        self.dialog.setWindowTitle(self._translator.text("config.title"))
        self.dialog.setMinimumWidth(460)

        layout = qt_widgets.QVBoxLayout(self.dialog)
        label = qt_widgets.QLabel(
            self._translator.text("config.explanation")
        )
        label.setWordWrap(True)
        layout.addWidget(label)

        self.combo = qt_widgets.QComboBox()
        for config in configs:
            self.combo.addItem(
                self._translator.text(f"config.{config}")
                if self._translator.text(f"config.{config}") != f"config.{config}"
                else CONVERSION_LABELS[config],
                config,
            )
        layout.addWidget(self.combo)

        self.jieba_status = qt_widgets.QLabel()
        self.jieba_status.setWordWrap(True)
        layout.addWidget(self.jieba_status)
        self.jieba_checkbox = qt_widgets.QCheckBox(self._translator.text("config.jieba"))
        self.jieba_checkbox.setToolTip(self._translator.text("config.jieba_tooltip"))
        layout.addWidget(self.jieba_checkbox)

        buttons = qt_widgets.QHBoxLayout()
        self.cancel_button = qt_widgets.QPushButton(self._translator.text("common.cancel"))
        self.continue_button = qt_widgets.QPushButton(self._translator.text("config.continue"))
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.continue_button)
        layout.addLayout(buttons)
        self.cancel_button.clicked.connect(self.dialog.reject)
        self.continue_button.clicked.connect(self._accept)
        self.combo.currentIndexChanged.connect(self._update_jieba_state)
        default_base = BASE_CONFIG_BY_JIEBA.get(default_config, default_config)
        selected_index = self.combo.findData(default_base)
        if selected_index >= 0:
            self.combo.setCurrentIndex(selected_index)
        self.jieba_checkbox.setChecked(default_config in self._jieba_configs.values())
        self._update_jieba_state()

    def _update_jieba_state(self) -> None:
        base_config = str(self.combo.currentData())
        plugin_config = self._jieba_configs.get(base_config)
        if plugin_config is None:
            self.jieba_checkbox.setChecked(False)
            self.jieba_checkbox.setEnabled(False)
        else:
            self.jieba_checkbox.setEnabled(True)
        if self._jieba_configs:
            self.jieba_status.setText(
                self._translator.text("config.jieba_available")
            )
        else:
            self.jieba_status.setText(
                self._translator.text("config.jieba_unavailable")
            )

    def _accept(self) -> None:
        base_config = str(self.combo.currentData())
        self.selected_config = (
            self._jieba_configs[base_config]
            if self.jieba_checkbox.isChecked() and base_config in self._jieba_configs
            else base_config
        )
        self.accepted = True
        self.dialog.accept()


class _ScopeDialog:
    """Qt view for selecting targets; all content reads happen after it closes."""

    def __init__(
        self,
        qt_widgets: Any,
        inventory: Tuple[TextFile, ...],
        initial_ids: Tuple[str, ...],
        language: str,
        translator: Translator,
        *,
        ignored_non_xhtml: int = 0,
    ) -> None:
        self._qt = qt_widgets
        self._inventory = inventory
        self._translator = translator
        self.accepted = False
        self.language = language
        self.ignored_non_xhtml = max(0, ignored_non_xhtml)
        self.dialog = qt_widgets.QDialog()
        self.dialog.setWindowTitle(translator.text("scope.title"))
        self.dialog.resize(700, 560)
        layout = qt_widgets.QVBoxLayout(self.dialog)

        language_row = qt_widgets.QHBoxLayout()
        self.language_label = qt_widgets.QLabel(translator.text("language.label"))
        language_row.addWidget(self.language_label)
        self.language_combo = qt_widgets.QComboBox()
        for code in SUPPORTED_LANGUAGES:
            self.language_combo.addItem(LANGUAGE_LABELS[code], code)
        self.language_combo.setCurrentIndex(max(0, self.language_combo.findData(language)))
        self.language_combo.currentIndexChanged.connect(self._language_changed)
        language_row.addWidget(self.language_combo)
        language_row.addStretch(1)
        layout.addLayout(language_row)

        self.single_radio = qt_widgets.QRadioButton(translator.text("scope.single"))
        self.selected_radio = qt_widgets.QRadioButton(translator.text("scope.selected"))
        self.all_radio = qt_widgets.QRadioButton(translator.text("scope.all"))
        self.selected_radio.setChecked(True)
        radio_row = qt_widgets.QHBoxLayout()
        for radio in (self.single_radio, self.selected_radio, self.all_radio):
            radio_row.addWidget(radio)
            radio.toggled.connect(self._refresh_enabled)
        layout.addLayout(radio_row)

        self.filter_edit = qt_widgets.QLineEdit()
        self.filter_edit.setPlaceholderText(translator.text("scope.filter"))
        self.filter_edit.textChanged.connect(self._refresh_list)
        layout.addWidget(self.filter_edit)
        self.list_widget = qt_widgets.QListWidget()
        layout.addWidget(self.list_widget)
        action_row = qt_widgets.QHBoxLayout()
        self.select_visible = qt_widgets.QPushButton(translator.text("scope.select_visible"))
        self.clear_visible = qt_widgets.QPushButton(translator.text("scope.clear_visible"))
        action_row.addWidget(self.select_visible)
        action_row.addWidget(self.clear_visible)
        action_row.addStretch(1)
        layout.addLayout(action_row)
        self.count_label = qt_widgets.QLabel()
        layout.addWidget(self.count_label)
        self.ignored_label = qt_widgets.QLabel()
        self.ignored_label.setWordWrap(True)
        layout.addWidget(self.ignored_label)

        button_row = qt_widgets.QHBoxLayout()
        self.cancel_button = qt_widgets.QPushButton(translator.text("common.cancel"))
        self.analyze_button = qt_widgets.QPushButton(translator.text("scope.analyze"))
        button_row.addStretch(1)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.analyze_button)
        layout.addLayout(button_row)
        self.cancel_button.clicked.connect(self.dialog.reject)
        self.analyze_button.clicked.connect(self._accept)
        self.select_visible.clicked.connect(lambda: self._set_visible(True))
        self.clear_visible.clicked.connect(lambda: self._set_visible(False))

        initial = set(initial_ids)
        for item in inventory:
            row = qt_widgets.QListWidgetItem(item.href)
            row.setData(qt_widgets.Qt.UserRole, item.file_id)
            row.setFlags(row.flags() | qt_widgets.Qt.ItemIsUserCheckable)
            row.setCheckState(
                qt_widgets.Qt.Checked if item.file_id in initial else qt_widgets.Qt.Unchecked
            )
            self.list_widget.addItem(row)
        self.list_widget.itemChanged.connect(self._item_changed)
        if len(initial_ids) == 1:
            self.single_radio.setChecked(True)
        elif not initial_ids:
            self.selected_radio.setChecked(True)
        self._refresh_enabled()
        self._refresh_count()

    def _item_changed(self, _item: Any) -> None:
        """Refresh counts and validity for direct checkbox changes."""

        self._refresh_count()
        self._update_analyze_enabled()

    def _language_changed(self) -> None:
        code = str(self.language_combo.currentData())
        self.language = code
        self._translator.set_language(code)
        self.dialog.setWindowTitle(self._translator.text("scope.title"))
        self.language_label.setText(self._translator.text("language.label"))
        self.single_radio.setText(self._translator.text("scope.single"))
        self.selected_radio.setText(self._translator.text("scope.selected"))
        self.all_radio.setText(self._translator.text("scope.all"))
        self.filter_edit.setPlaceholderText(self._translator.text("scope.filter"))
        self.select_visible.setText(self._translator.text("scope.select_visible"))
        self.clear_visible.setText(self._translator.text("scope.clear_visible"))
        self.cancel_button.setText(self._translator.text("common.cancel"))
        self.analyze_button.setText(self._translator.text("scope.analyze"))
        self._refresh_count()
        self._update_analyze_enabled()

    def _checked_ids(self) -> Tuple[str, ...]:
        checked = self._qt.Qt.Checked
        return tuple(
            self.list_widget.item(index).data(self._qt.Qt.UserRole)
            for index in range(self.list_widget.count())
            if self.list_widget.item(index).checkState() == checked
        )

    def selected_ids(self) -> Tuple[str, ...]:
        return self._checked_ids()

    def _refresh_list(self) -> None:
        query = self.filter_edit.text().strip().lower()
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            item.setHidden(bool(query) and query not in item.text().lower())
        self._refresh_count()

    def _set_visible(self, checked: bool) -> None:
        state = self._qt.Qt.Checked if checked else self._qt.Qt.Unchecked
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            if not item.isHidden():
                item.setCheckState(state)
        self._refresh_count()

    def _refresh_count(self) -> None:
        total = self.list_widget.count()
        if self.all_radio.isChecked():
            self.count_label.setText(
                self._translator.text("scope.all_count", total=total)
            )
        else:
            selected = len(self._checked_ids())
            self.count_label.setText(
                self._translator.text("scope.selected_count", selected=selected, total=total)
            )
        if self.ignored_non_xhtml:
            self.ignored_label.setText(
                self._translator.text(
                    "scope.ignored_non_xhtml", count=self.ignored_non_xhtml
                )
            )
            self.ignored_label.show()
        else:
            self.ignored_label.clear()
            self.ignored_label.hide()

    def _refresh_enabled(self) -> None:
        if not hasattr(self, "filter_edit"):
            return
        custom = self.single_radio.isChecked() or self.selected_radio.isChecked()
        self.filter_edit.setEnabled(custom)
        self.list_widget.setEnabled(custom)
        self.select_visible.setEnabled(custom)
        self.clear_visible.setEnabled(custom)
        self._refresh_count()
        self._update_analyze_enabled()

    def _update_analyze_enabled(self) -> None:
        if not hasattr(self, "analyze_button"):
            return
        count = len(self._checked_ids())
        valid = bool(self._inventory)
        if self.single_radio.isChecked():
            valid = count == 1
        elif self.selected_radio.isChecked():
            valid = count > 0
        self.analyze_button.setEnabled(valid)

    def _accept(self) -> None:
        checked_count = len(self.selected_ids())
        try:
            scope = Scope.SINGLE if self.single_radio.isChecked() else (
                Scope.ALL_XHTML if self.all_radio.isChecked() else Scope.SELECTED
            )
            selection = resolve_target_selection(self._inventory, scope, self.selected_ids())
            if selection.empty:
                raise ScopeSelectionError(self._translator.text("scope.none"))
        except ScopeSelectionError:
            message_key = (
                "error.scope_exactly_one"
                if self.single_radio.isChecked() and checked_count != 1
                else "scope.none"
            )
            self._qt.QMessageBox.warning(
                self.dialog,
                self._translator.text("scope.title"),
                self._translator.text(message_key),
            )
            return
        self.scope = scope
        self.accepted = True
        self.dialog.accept()
