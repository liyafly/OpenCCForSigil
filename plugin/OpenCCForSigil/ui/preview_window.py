"""Minimal Preview UI for the first interactive conversion phase."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence, Tuple

from core.preview import PreviewFilter, PreviewSession
from core.models import TokenChange
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
    back_to_settings: bool = False
    checkpoint_notice_shown: bool = False


@dataclass(frozen=True)
class ScopeOutcome:
    accepted: bool
    selection: TargetSelection | None
    language: str


class ProgressReporter:
    """A lightweight progress view driven by workflow file boundaries."""

    def __init__(self, qt_widgets: Any, total: int, parent: Any = None) -> None:
        self._qt = qt_widgets
        self._cancelled = False
        self._closed = False
        self._phase = "analyzing"
        self._total = max(int(total), 1)
        self._value = 0
        self.dialog = qt_widgets.QProgressDialog(
            "", _translator.text("common.cancel"), 0, self._total, parent
        )
        self.dialog.setWindowTitle(_translator.text("progress.title"))
        # A parent supplied by a future plugin-owned QWidget scopes modality to
        # that window.  The current entry point has no stable host QWidget, so
        # the unparented dialog is application-modal only within this plugin's
        # QApplication; Sigil runs plugins in a separate process.
        set_window_modality = getattr(self.dialog, "setWindowModality", None)
        qt = getattr(qt_widgets, "Qt", None)
        modality_name = "WindowModal" if parent is not None else "ApplicationModal"
        modality = getattr(qt, modality_name, None)
        if callable(set_window_modality) and modality is not None:
            set_window_modality(modality)
        # Qt's default minimum duration is intentionally conservative and can
        # leave a synchronous conversion looking frozen for several seconds.
        # This operation already has real file boundaries, so render the
        # progress window immediately and paint its initial state before the
        # first read/conversion begins.
        set_minimum_duration = getattr(self.dialog, "setMinimumDuration", None)
        if callable(set_minimum_duration):
            set_minimum_duration(0)
        self.dialog.setAutoClose(False)
        self.dialog.setAutoReset(False)
        self.dialog.canceled.connect(self._mark_cancelled)
        self.dialog.setMaximum(self._total)
        self.dialog.setValue(0)
        self.dialog.setLabelText(
            _translator.text(
                "progress.status",
                phase=_translator.text("progress.phase.analyzing"),
                index=0,
                total=max(int(total), 0),
                file="…",
            )
        )
        self.dialog.show()
        self._process_events()

    def _mark_cancelled(self) -> None:
        self._cancelled = True

    def update(self, phase: str, index: int, total: int, href: str) -> None:
        phase = str(phase)
        phase_total = max(int(total), 1)
        if phase != self._phase:
            # Each workflow phase owns its own count.  Reset to zero before
            # painting the first item so a shorter phase never looks like a
            # backwards jump in one global counter.
            self._phase = phase
            self._total = phase_total
            self._value = 0
            self.dialog.setMaximum(self._total)
            self.dialog.setValue(0)
        elif phase_total != self._total:
            self._total = phase_total
            self._value = min(self._value, self._total)
            self.dialog.setMaximum(self._total)

        requested = max(int(index), 0)
        self._value = min(max(requested, self._value), self._total)
        self.dialog.setValue(self._value)
        self.dialog.setLabelText(
            _translator.text(
                "progress.status",
                phase=_translator.text(f"progress.phase.{self._phase}"),
                index=self._value,
                total=total,
                file=href,
            )
        )
        self._process_events()

    def cancelled(self) -> bool:
        self._process_events()
        return self._cancelled

    def disable_cancel(self) -> None:
        """Remove the cancel affordance for a non-cancellable phase."""

        set_cancel_button = getattr(self.dialog, "setCancelButton", None)
        if callable(set_cancel_button):
            set_cancel_button(None)
        self._cancelled = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.dialog.close()

    def _process_events(self) -> None:
        process_events = getattr(self._qt.QApplication, "processEvents", None)
        if callable(process_events):
            process_events()


_translator = Translator("en")
_jieba_unavailable_reason: str | None = None

_LOCAL_TEXT = {
    "en": {
        "scope.spine": "Spine",
        "scope.spine_count": "Spine files: {total}",
        "preview.accept_filter": "Accept filtered",
        "preview.skip_filter": "Skip filtered",
        "preview.filter_file": "File",
        "preview.filter_category": "Category",
        "preview.filter_risk": "Risk",
        "preview.filter_all": "All",
        "preview.back_settings": "Back to settings",
        "preview.checkpoint_title": "Checkpoint required",
        "preview.checkpoint_message": (
            "Plugin changes cannot be undone with Ctrl+Z. Create a Sigil Checkpoint before applying.\n\n"
            "Continue applying the selected changes?"
        ),
        "preview.checkpoint_yes": "I created a Checkpoint; continue",
        "preview.checkpoint_no": "Cancel",
        "preview.checkpoint_hide": "Do not show again",
        "preview.diagnostics": "Plan diagnostics: {details}",
        "preview.diagnostic_detail": "Diagnostics: {details}",
        "preview.export": "Export report",
        "preview.export_full_diff": "Include full diff",
    },
    "zh-Hans": {
        "scope.spine": "Spine 正文",
        "scope.spine_count": "Spine 文件数：{total}",
        "preview.accept_filter": "接受筛选项",
        "preview.skip_filter": "跳过筛选项",
        "preview.filter_file": "文件",
        "preview.filter_category": "类别",
        "preview.filter_risk": "风险",
        "preview.filter_all": "全部",
        "preview.back_settings": "返回设置",
        "preview.checkpoint_title": "需要建立 Checkpoint",
        "preview.checkpoint_message": "插件修改无法用 Ctrl+Z 撤销。应用前请先在 Sigil 中建立 Checkpoint。\n\n继续应用已选择的变化吗？",
        "preview.checkpoint_yes": "我已建立 Checkpoint，继续",
        "preview.checkpoint_no": "取消",
        "preview.checkpoint_hide": "以后不再提示",
        "preview.diagnostics": "计划诊断：{details}",
        "preview.diagnostic_detail": "诊断：{details}",
        "preview.export": "导出报告",
        "preview.export_full_diff": "包含完整差异",
    },
    "zh-Hant": {
        "scope.spine": "Spine 正文",
        "scope.spine_count": "Spine 檔案數：{total}",
        "preview.accept_filter": "接受篩選項目",
        "preview.skip_filter": "略過篩選項目",
        "preview.filter_file": "檔案",
        "preview.filter_category": "類別",
        "preview.filter_risk": "風險",
        "preview.filter_all": "全部",
        "preview.back_settings": "返回設定",
        "preview.checkpoint_title": "需要建立 Checkpoint",
        "preview.checkpoint_message": "外掛程式修改無法用 Ctrl+Z 復原。套用前請先在 Sigil 中建立 Checkpoint。\n\n要繼續套用已選取的變化嗎？",
        "preview.checkpoint_yes": "我已建立 Checkpoint，繼續",
        "preview.checkpoint_no": "取消",
        "preview.checkpoint_hide": "以後不再提示",
        "preview.diagnostics": "計畫診斷：{details}",
        "preview.diagnostic_detail": "診斷：{details}",
        "preview.export": "匯出報告",
        "preview.export_full_diff": "包含完整差異",
    },
}


def _ui_text(key: str, **values: object) -> str:
    """Use shipped catalogs first and local fallback text for new preview keys."""

    value = _translator.text(key, **values)
    if value != key:
        return value
    language = _translator.language if _translator.language in _LOCAL_TEXT else "en"
    return _LOCAL_TEXT[language].get(key, _LOCAL_TEXT["en"].get(key, key)).format(**values)


def set_jieba_status(reason: str | None) -> None:
    global _jieba_unavailable_reason
    _jieba_unavailable_reason = reason


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
    spine_ids = _spine_ids(adapter)
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
        spine_ids=spine_ids,
    )
    exec_method = getattr(dialog.dialog, "exec", None) or dialog.dialog.exec_
    exec_method()
    if not dialog.accepted:
        return ScopeOutcome(False, None, dialog.language)
    _translator.set_language(dialog.language)
    selection = resolve_target_selection(
        inventory,
        dialog.scope,
        dialog.spine_ids if dialog.scope is Scope.SPINE else dialog.selected_ids(),
    )
    return ScopeOutcome(True, selection, dialog.language)


def create_progress_reporter(total: int, parent: Any = None) -> ProgressReporter:
    """Create a progress reporter using Sigil's already available Qt runtime."""

    qt_widgets = _load_qt_widgets()
    _ensure_application(qt_widgets)
    return ProgressReporter(qt_widgets, total, parent)


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


def _spine_ids(adapter: Any) -> Tuple[str, ...]:
    """Read the spine manifest ids without reading any document content."""

    text_files = getattr(adapter, "text_files", None)
    if not callable(text_files):
        return ()
    try:
        return tuple(file_id for file_id, _href in text_files(Scope.SPINE))
    except (AttributeError, TypeError, ValueError):
        return ()


def show_preview(planned: Sequence[PlannedDocument]) -> PreviewOutcome:
    """Show a preview and return the sessions containing user decisions."""

    qt_widgets = _load_qt_widgets()
    previews = tuple(PreviewSession(item.plan) for item in planned)
    _ensure_application(qt_widgets)
    dialog = _PreviewDialog(qt_widgets, planned, previews)
    exec_method = getattr(dialog.dialog, "exec", None) or dialog.dialog.exec_
    exec_method()
    return PreviewOutcome(
        accepted=dialog.applied,
        previews=previews,
        back_to_settings=dialog.back_to_settings,
        checkpoint_notice_shown=dialog.checkpoint_notice_shown,
    )


def show_result(
    *,
    status: str,
    files_scanned: int,
    files_changed: int,
    accepted_changes: int,
    skipped_changes: int,
    files_not_written: int | None = None,
    files_without_changes: int = 0,
    failed_file: str | None = None,
) -> None:
    """Show a concise localized terminal result after the write boundary."""

    qt_widgets = _load_qt_widgets()
    _ensure_application(qt_widgets)
    not_written = (
        max(files_scanned - files_changed, 0)
        if files_not_written is None
        else max(int(files_not_written), 0)
    )
    result_values = _result_count_values(
        files_scanned=files_scanned,
        files_changed=files_changed,
        accepted_changes=accepted_changes,
        skipped_changes=skipped_changes,
        files_not_written=not_written,
        files_without_changes=files_without_changes,
    )
    if status == "partial_failure":
        message = _translator.text(
            "result.partial",
            **result_values,
            failed_file=failed_file or "?",
        )
        method = getattr(qt_widgets.QMessageBox, "warning")
    elif status == "cancelled":
        message = _translator.text("result.cancelled")
        method = getattr(qt_widgets.QMessageBox, "information")
    elif accepted_changes == 0 and skipped_changes:
        message = _translator.text(
            "result.skipped",
            **result_values,
        )
        method = getattr(qt_widgets.QMessageBox, "information")
    elif accepted_changes == 0:
        message = _translator.text("result.noop", **result_values)
        method = getattr(qt_widgets.QMessageBox, "information")
    else:
        message = _translator.text(
            "result.done",
            **result_values,
        )
        method = getattr(qt_widgets.QMessageBox, "information")
    method(None, _translator.text("app.title"), message)


def _result_count_values(
    *,
    files_scanned: int,
    files_changed: int,
    accepted_changes: int,
    skipped_changes: int,
    files_not_written: int,
    files_without_changes: int,
) -> dict[str, str]:
    return {
        "files": _result_count_phrase("files", files_scanned),
        "written": _result_count_phrase("files", files_changed),
        "accepted": _result_count_phrase("changes", accepted_changes),
        "skipped": _result_count_phrase("changes", skipped_changes),
        "not_written": _result_count_phrase("not_written", files_not_written),
        "unchanged": _result_count_phrase("unchanged", files_without_changes),
    }


def _result_count_phrase(kind: str, count: int) -> str:
    value = max(int(count), 0)
    form = "one" if value == 1 else "many"
    return _translator.text(f"result.{kind}_{form}", count=value)


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
        # Plans are immutable, so the preview rows never change identity.  A
        # cached change object avoids doing a linear ``next(...)`` lookup for
        # every row every time a bulk decision refreshes the list.
        self._entries: Tuple[Tuple[PreviewSession, TokenChange], ...] = tuple(
            (preview, change)
            for preview in previews
            for change in preview.changes
        )
        self.applied = False
        self.back_to_settings = False
        self.checkpoint_notice_shown = False

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

        filter_row = qt.QHBoxLayout()
        self.file_filter = qt.QComboBox()
        self.category_filter = qt.QComboBox()
        self.risk_filter = qt.QComboBox()
        self._populate_filter(self.file_filter, _ui_text("preview.filter_file"),
                              sorted({change.file_id for _, change in self._entries}))
        self._populate_filter(self.category_filter, _ui_text("preview.filter_category"),
                              sorted({change.category for _, change in self._entries}))
        self._populate_filter(self.risk_filter, _ui_text("preview.filter_risk"),
                              sorted({change.risk for _, change in self._entries}))
        for widget in (self.file_filter, self.category_filter, self.risk_filter):
            filter_row.addWidget(widget)
            widget.currentIndexChanged.connect(self._refresh)
        layout.addLayout(filter_row)

        self.list_widget = qt.QListWidget()
        self.list_widget.currentRowChanged.connect(self._show_current)
        layout.addWidget(self.list_widget)

        self.detail = qt.QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMinimumHeight(180)
        layout.addWidget(self.detail)

        buttons = qt.QHBoxLayout()
        self.accept_this_button = qt.QPushButton(_translator.text("preview.accept_this"))
        self.reject_this_button = qt.QPushButton(_translator.text("preview.skip_this"))
        self.accept_file_button = qt.QPushButton(_translator.text("preview.accept_file"))
        self.reject_file_button = qt.QPushButton(_translator.text("preview.skip_file"))
        self.accept_all_button = qt.QPushButton(_translator.text("preview.accept_all"))
        self.reject_all_button = qt.QPushButton(_translator.text("preview.skip_all"))
        self.accept_filter_button = qt.QPushButton(_ui_text("preview.accept_filter"))
        self.reject_filter_button = qt.QPushButton(_ui_text("preview.skip_filter"))
        self.export_button = qt.QPushButton(_ui_text("preview.export"))
        self.export_full_diff = qt.QCheckBox(_ui_text("preview.export_full_diff"))
        self.export_full_diff.setChecked(False)
        self.apply_button = qt.QPushButton(_translator.text("preview.apply"))
        self.back_settings_button = qt.QPushButton(_ui_text("preview.back_settings"))
        self.cancel_button = qt.QPushButton(_translator.text("common.cancel"))
        for button in (self.accept_this_button, self.reject_this_button,
                       self.accept_file_button, self.reject_file_button,
                       self.accept_filter_button, self.reject_filter_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        tools = qt.QHBoxLayout()
        for button in (self.accept_all_button, self.reject_all_button,
                       self.export_button, self.export_full_diff):
            tools.addWidget(button)
        layout.addLayout(tools)
        actions = qt.QHBoxLayout()
        actions.addStretch(1)
        for button in (self.back_settings_button, self.cancel_button, self.apply_button):
            actions.addWidget(button)
        layout.addLayout(actions)

        self.accept_this_button.clicked.connect(self._accept_this)
        self.reject_this_button.clicked.connect(self._reject_this)
        self.accept_file_button.clicked.connect(self._accept_file)
        self.reject_file_button.clicked.connect(self._reject_file)
        self.accept_all_button.clicked.connect(self._accept_all)
        self.reject_all_button.clicked.connect(self._reject_all)
        self.accept_filter_button.clicked.connect(lambda: self._decide_filtered(True))
        self.reject_filter_button.clicked.connect(lambda: self._decide_filtered(False))
        self.export_button.clicked.connect(self._export_preview)
        self.apply_button.clicked.connect(self._apply)
        self.back_settings_button.clicked.connect(self._back_to_settings)
        self.cancel_button.clicked.connect(self.dialog.reject)
        self.export_button.setEnabled(self._export_service() is not None)

    @staticmethod
    def _export_service():
        try:
            from ui.run_options import get_run_services
        except (ImportError, AttributeError):
            return None
        try:
            services = get_run_services()
        except (AttributeError, TypeError):
            return None
        return getattr(services, "export_preview", None) if services is not None else None

    def _export_preview(self) -> None:
        export = self._export_service()
        if export is None:
            return
        checkbox = getattr(self, "export_full_diff", None)
        include_full_diff = bool(checkbox is not None and checkbox.isChecked())
        export(self._planned, self._previews, include_full_diff, self._qt, self.dialog)

    @staticmethod
    def _populate_filter(combo: Any, label: str, values: Sequence[str]) -> None:
        combo.addItem(f"{label}: {_ui_text('preview.filter_all')}", None)
        for value in values:
            combo.addItem(str(value), str(value))

    def _current_filter(self) -> PreviewFilter:
        def data(name: str) -> str | None:
            combo = getattr(self, name, None)
            if combo is None or not callable(getattr(combo, "currentData", None)):
                return None
            value = combo.currentData()
            return str(value) if value else None

        return PreviewFilter(
            file_id=data("file_filter"),
            category=data("category_filter"),
            risk=data("risk_filter"),
        )

    def _visible_entries(self) -> Tuple[Tuple[PreviewSession, TokenChange], ...]:
        current = self._current_filter()
        return tuple((preview, change) for preview, change in self._entries if current.matches(change))

    @staticmethod
    def _truncate(value: object, limit: int = 96) -> str:
        text = str(value)
        if len(text) <= limit:
            return text
        return text[: max(1, limit - 1)] + "…"

    def _diagnostics_for_file(self, file_id: str | None = None) -> Tuple[str, ...]:
        diagnostics = []
        for planned in getattr(self, "_planned", ()):
            plan = getattr(planned, "plan", None)
            if plan is None or (file_id and getattr(plan, "file_id", "") != file_id):
                continue
            for diagnostic in getattr(plan, "diagnostics", ()):
                code = str(getattr(diagnostic, "code", ""))
                message = str(getattr(diagnostic, "message", ""))
                diagnostics.append(f"{code}: {message}" if message else code)
        return tuple(dict.fromkeys(diagnostics))

    def _refresh(self) -> None:
        visible_entries = self._visible_entries()
        current_row = self.list_widget.currentRow()
        self.list_widget.blockSignals(True)
        set_updates_enabled = getattr(self.list_widget, "setUpdatesEnabled", None)
        if callable(set_updates_enabled):
            set_updates_enabled(False)
        try:
            if self.list_widget.count() != len(visible_entries):
                self.list_widget.clear()
                for preview, change in visible_entries:
                    self.list_widget.addItem(self._entry_text(preview, change))
            else:
                for index, (preview, change) in enumerate(visible_entries):
                    item = self.list_widget.item(index)
                    if item is not None:
                        item.setText(self._entry_text(preview, change))
        finally:
            if callable(set_updates_enabled):
                set_updates_enabled(True)
            self.list_widget.blockSignals(False)

        if visible_entries:
            row = current_row if 0 <= current_row < len(visible_entries) else 0
            self.list_widget.setCurrentRow(row)
            self._show_current(row)
        else:
            self.detail.setPlainText(_translator.text("preview.no_changes"))
        self._update_summary()

    @staticmethod
    def _entry_text(preview: PreviewSession, change: TokenChange) -> str:
        decision = preview.decision(change.change_id)
        prefix = "?" if decision is None else "✓" if decision.value.startswith("accept") else "×"
        source = _PreviewDialog._truncate(change.source)
        target = _PreviewDialog._truncate(change.target)
        return f"{prefix} {change.file_id}: {source!r} → {target!r}"

    def _update_summary(self) -> None:
        totals = {"total": 0, "accepted": 0, "rejected": 0, "undecided": 0}
        for preview in self._previews:
            for key, value in preview.summary().items():
                totals[key] += value
        summary = _translator.text("preview.summary", files=len(self._previews), **totals)
        diagnostics = self._diagnostics_for_file()
        if diagnostics:
            summary += "\n" + _ui_text("preview.diagnostics", details="; ".join(diagnostics))
        self.summary.setText(summary)
        has_current = bool(self._visible_entries())
        for name in (
            "accept_this_button",
            "reject_this_button",
            "accept_file_button",
            "reject_file_button",
            "accept_filter_button",
            "reject_filter_button",
        ):
            button = getattr(self, name, None)
            if button is not None:
                button.setEnabled(has_current)
        # An explicit repeat of a bulk action is allowed to reverse prior
        # per-item decisions, so both global buttons stay available while the
        # preview contains changes.  Applying remains blocked until every
        # change has a decision, including a preview with no changes.
        has_entries = bool(self._entries)
        for name in ("accept_all_button", "reject_all_button"):
            button = getattr(self, name, None)
            if button is not None:
                button.setEnabled(has_entries)
        self.apply_button.setEnabled(totals["undecided"] == 0)

    def _show_current(self, row: int) -> None:
        visible_entries = self._visible_entries()
        if row < 0 or row >= len(visible_entries):
            self.detail.clear()
            return
        preview, change = visible_entries[row]
        diagnostics = self._diagnostics_for_file(change.file_id)
        diagnostic_text = (
            "\n" + _ui_text("preview.diagnostic_detail", details="; ".join(diagnostics))
            if diagnostics
            else ""
        )
        self.detail.setPlainText(
            f"{_translator.text('preview.rule')}: {change.rule_source}\n"
            f"{_translator.text('preview.category')}: {change.category}    "
            f"{_translator.text('preview.risk')}: {change.risk}\n"
            f"{_translator.text('preview.before')}: "
            f"{change.context_before}{change.source}{change.context_after}\n"
            f"{_translator.text('preview.change')}: {change.source!r} → {change.target!r}"
            f"{diagnostic_text}"
        )

    def _current_entry(self):
        row = self.list_widget.currentRow()
        visible_entries = self._visible_entries()
        if row < 0 or row >= len(visible_entries):
            return None
        return visible_entries[row]

    def _accept_this(self) -> None:
        entry = self._current_entry()
        if entry is None:
            return
        self._decide_entry(entry, True)

    def _reject_this(self) -> None:
        entry = self._current_entry()
        if entry is None:
            return
        self._decide_entry(entry, False)

    def _decide_entry(self, entry, accepted):
        preview, change = entry
        if change.group_id:
            self._decide_group(change.group_id, accepted)
            self._refresh()
        else:
            (preview.accept_this if accepted else preview.reject_this)(change.change_id)
            self._refresh_current()

    def _decide_group(self, group_id, accepted):
        for preview, change in self._entries:
            if change.group_id == group_id:
                (preview.accept_this if accepted else preview.reject_this)(change.change_id)

    def _decide_filtered(self, accepted: bool) -> None:
        visible_entries = self._visible_entries()
        groups = {change.group_id for _preview, change in visible_entries if change.group_id}
        for preview, change in visible_entries:
            if not change.group_id:
                (preview.accept_this if accepted else preview.reject_this)(change.change_id)
        for group_id in groups:
            self._decide_group(group_id, accepted)
        self._refresh()

    def _refresh_current(self) -> None:
        row = self.list_widget.currentRow()
        visible_entries = self._visible_entries()
        if row < 0 or row >= len(visible_entries):
            self._update_summary()
            return
        item = self.list_widget.item(row)
        if item is not None:
            preview, change = visible_entries[row]
            item.setText(self._entry_text(preview, change))
        self._show_current(row)
        self._update_summary()

    def _accept_file(self) -> None:
        entry = self._current_entry()
        if entry is None:
            return
        entry[0].accept_all(overwrite=True)
        for change in entry[0].changes:
            if change.group_id:
                self._decide_group(change.group_id, True)
        self._refresh()

    def _reject_file(self) -> None:
        entry = self._current_entry()
        if entry is None:
            return
        entry[0].reject_all(overwrite=True)
        for change in entry[0].changes:
            if change.group_id:
                self._decide_group(change.group_id, False)
        self._refresh()

    def _accept_all(self) -> None:
        for preview in self._previews:
            preview.accept_all(overwrite=True)
        self._refresh()

    def _reject_all(self) -> None:
        for preview in self._previews:
            preview.reject_all(overwrite=True)
        self._refresh()

    def _back_to_settings(self) -> None:
        if self.applied:
            return
        self.back_to_settings = True
        self.dialog.reject()

    def _checkpoint_confirm(self) -> bool:
        if not any(preview.summary()["accepted"] for preview in self._previews):
            return True
        from ui.run_options import get_run_services
        services = get_run_services()
        if services is not None and not services.checkpoint_notice_enabled():
            return True
        message_box = getattr(self._qt, "QMessageBox", None)
        if not callable(message_box):
            return True
        self.checkpoint_notice_shown = True
        box = message_box(self.dialog)
        box.setWindowTitle(_ui_text("preview.checkpoint_title"))
        box.setText(_ui_text("preview.checkpoint_message"))
        box.setIcon(message_box.Warning)
        accept = box.addButton(_ui_text("preview.checkpoint_yes"), message_box.AcceptRole)
        cancel = box.addButton(_ui_text("preview.checkpoint_no"), message_box.RejectRole)
        box.setDefaultButton(cancel)
        hide = self._qt.QCheckBox(_ui_text("preview.checkpoint_hide"))
        box.setCheckBox(hide)
        box.exec()
        accepted = box.clickedButton() is accept
        if accepted and hide.isChecked() and services is not None:
            services.hide_checkpoint_notice()
        return accepted

    def _apply(self) -> None:
        if self.applied:
            return
        if any(preview.undecided() for preview in self._previews):
            self._update_summary()
            return
        if not self._checkpoint_confirm():
            return
        self.applied = True
        # Disable before accepting the dialog so a queued/re-entrant click
        # cannot submit the same preview twice.
        self.apply_button.setEnabled(False)
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

        from ui.run_options import RunOptionsPanel
        self.options_panel = RunOptionsPanel(qt_widgets, translator, layout)
        self.options_panel.bind(self._get_config, self._set_config, self.dialog)

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

    def _get_config(self):
        base = str(self.combo.currentData())
        return self._jieba_configs.get(base, base) if self.jieba_checkbox.isChecked() else base

    def _set_config(self, config):
        base = BASE_CONFIG_BY_JIEBA.get(config, config)
        index = self.combo.findData(base)
        if index < 0 or (config != base and config not in self._jieba_configs.values()):
            raise ValueError("profile configuration is unavailable on this host")
        self.combo.setCurrentIndex(index)
        self.jieba_checkbox.setChecked(config != base)
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
                + ("\n" + _jieba_unavailable_reason if _jieba_unavailable_reason else "")
            )

    def _accept(self) -> None:
        from transforms.language_tags import target_language
        from ui.run_options import ConfigurationChoice

        base_config = str(self.combo.currentData())
        config = (
            self._jieba_configs[base_config]
            if self.jieba_checkbox.isChecked() and base_config in self._jieba_configs
            else base_config
        )
        options = self.options_panel.values()
        try:
            self.options_panel.validate(config)
            target_language(config, options["language_metadata"], options["language_preset"],
                            options["language_region"])
        except ValueError as exc:
            self._qt.QMessageBox.warning(self.dialog, self._translator.text("config.title"), str(exc))
            return
        self.selected_config = ConfigurationChoice(config, options)
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
        spine_ids: Tuple[str, ...] = (),
    ) -> None:
        self._qt = qt_widgets
        self._inventory = inventory
        self._translator = translator
        self.accepted = False
        self.language = language
        self.ignored_non_xhtml = max(0, ignored_non_xhtml)
        self.spine_ids = tuple(file_id for file_id in spine_ids if file_id)
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
        self.spine_radio = qt_widgets.QRadioButton(_ui_text("scope.spine"))
        self.all_radio = qt_widgets.QRadioButton(translator.text("scope.all"))
        self.selected_radio.setChecked(True)
        radio_row = qt_widgets.QHBoxLayout()
        for radio in (self.single_radio, self.selected_radio, self.spine_radio, self.all_radio):
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
        self.spine_radio.setText(_ui_text("scope.spine"))
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
        self.list_widget.blockSignals(True)
        try:
            for index in range(self.list_widget.count()):
                item = self.list_widget.item(index)
                if not item.isHidden():
                    item.setCheckState(state)
        finally:
            self.list_widget.blockSignals(False)
        self._refresh_count()
        self._update_analyze_enabled()

    def _refresh_count(self) -> None:
        total = self.list_widget.count()
        if self.all_radio.isChecked():
            self.count_label.setText(
                self._translator.text("scope.all_count", total=total)
            )
        elif self.spine_radio.isChecked():
            self.count_label.setText(_ui_text("scope.spine_count", total=len(self.spine_ids)))
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
        self.spine_radio.setEnabled(bool(self.spine_ids))
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
        elif self.spine_radio.isChecked():
            valid = bool(self.spine_ids)
        self.analyze_button.setEnabled(valid)

    def _accept(self) -> None:
        checked_count = len(self.selected_ids())
        try:
            scope = Scope.SINGLE if self.single_radio.isChecked() else (
                Scope.ALL_XHTML
                if self.all_radio.isChecked()
                else Scope.SPINE
                if self.spine_radio.isChecked()
                else Scope.SELECTED
            )
            ids = self.spine_ids if scope is Scope.SPINE else self.selected_ids()
            selection = resolve_target_selection(self._inventory, scope, ids)
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
