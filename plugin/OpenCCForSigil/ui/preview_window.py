"""Minimal Preview UI for the first interactive conversion phase."""

from __future__ import annotations

from bisect import bisect_left
from collections import Counter
from dataclasses import dataclass
from html import unescape
from typing import Any
from collections.abc import Sequence

from core.preview import (
    PreviewDecision,
    PreviewFilter,
    PreviewSession,
)
from core.models import TokenChange
from core.workflow import PlannedDocument
from opencc_backend.configs import (
    JIEBA_CONFIG_BY_BASE,
    V1_CONFIGS,
)
from sigil.scope import TargetSelection
from ui.qt import ensure_application, enum_value as _enum_value, exec_dialog, load_qt
from ui.i18n import (
    Translator,
    configuration_label,
    diagnostic_summary,
    plugin_window_title,
)
from ui.window_state import restore_window_size, save_window_size
from ui.run_summary import run_summary_data
from ui.preview_batch import plan_batch_decision
from ui.config_dialog import _ConversionConfigDialog
from ui.diagnostics_panel import _DiagnosticPanel, _diagnostic_record_count, _diagnostic_records
from ui.preview_history import (
    _DecisionHistoryChange,
    _DecisionHistoryOperation,
    _ScopedBulkDecisionHistoryOperation,
)
from ui.preview_table import (
    _create_preview_table_model,
    _group_explanation_key,
    _group_feedback_key,
    _single_line,
    _source_context,
    _text_context,
)
from ui.progress import ProgressReporter
from ui.qt import UIUnavailableError
from ui.scope_dialog import (
    _ScopeDialog,
    _ordered_scope_inventory,
    _selected_xhtml_ids_and_ignored,
    _spine_ids,
)

# Re-exported so existing ``ui.preview_window`` imports keep working after the
# dialog, table and diagnostics helpers moved into their own modules.
from ui.diagnostics_panel import (
    _LINE_BREAK as _LINE_BREAK,
    _DiagnosticRecord as _DiagnosticRecord,
    _diagnostic_excerpt as _diagnostic_excerpt,
    _index_change_spans as _index_change_spans,
    _line_column_for_offset as _line_column_for_offset,
    _source_line_starts as _source_line_starts,
)
from ui.preview_table import (
    _PREVIEW_COLUMNS as _PREVIEW_COLUMNS,
    _PreviewTableData as _PreviewTableData,
    _format_change_row as _format_change_row,
    _group_marker_key as _group_marker_key,
    format_change_row as format_change_row,
)
from ui.scope_dialog import (
    _information_icon_label as _information_icon_label,
    _recovery_notice_text as _recovery_notice_text,
    _set_scope_banner_surface as _set_scope_banner_surface,
)

_DECISION_VALUES = tuple(PreviewDecision)
_DECISION_TO_CODE = {decision: index + 1
                     for index, decision in enumerate(_DECISION_VALUES)}
_ACCEPTED_DECISION_CODES = tuple(
    _DECISION_TO_CODE[decision]
    for decision in _DECISION_VALUES if decision.value.startswith("accept")
)
_REJECTED_DECISION_CODES = tuple(
    _DECISION_TO_CODE[decision]
    for decision in _DECISION_VALUES if not decision.value.startswith("accept")
)


@dataclass(frozen=True)
class PreviewOutcome:
    accepted: bool
    previews: tuple[PreviewSession, ...]
    back_to_settings: bool = False
    checkpoint_notice_shown: bool = False


@dataclass(frozen=True)
class ScopeOutcome:
    accepted: bool
    selection: TargetSelection | None
    language: str
    configuration: object | None = None


CONFIG_SELECTION_ORDER = V1_CONFIGS


def _load_ui_qt(translator: Translator):
    try:
        return load_qt()
    except RuntimeError as exc:
        raise UIUnavailableError(translator.text("error.ui_unavailable")) from exc


def choose_scope(
    adapter: Any,
    *,
    initial_language: str = "en",
    notice=(),
    initial_selection: TargetSelection | None = None,
    translator: Translator | None = None,
    ui_preferences=None,
    save_ui_preferences=None,
    available_configs: Sequence[str],
    default_config: str = "s2t",
    jieba_probe=None,
    initial_options=None,
    metadata_available=True,
    services=None,
) -> ScopeOutcome:
    """Choose a frozen XHTML target set after enumerating metadata only."""

    inventory = tuple(adapter.text_file_inventory())
    selected_ids, ignored_non_xhtml = _selected_xhtml_ids_and_ignored(adapter, inventory)
    initial_scope = None
    if initial_selection is not None:
        selected_ids = tuple(initial_selection.file_ids)
        initial_scope = initial_selection.scope
    spine_ids = _spine_ids(adapter)
    inventory = _ordered_scope_inventory(inventory, spine_ids)
    nav_getter = getattr(adapter, "nav_id", None)
    nav_id = nav_getter() if callable(nav_getter) else None
    translator = translator or Translator(initial_language or "en")
    language = initial_language or translator.language
    translator.set_language(language)
    qt_widgets = _load_ui_qt(translator)
    ensure_application(qt_widgets, language=language)
    configs = tuple(config for config in CONFIG_SELECTION_ORDER
                    if config in set(available_configs))
    if not configs:
        raise UIUnavailableError(translator.text("error.no_config"))
    jieba_configs = {
        base: plugin
        for base, plugin in JIEBA_CONFIG_BY_BASE.items()
        if plugin in set(available_configs)
    }
    outer = qt_widgets.QDialog()
    outer.setWindowTitle(plugin_window_title(
        translator, translator.text("main.title")))
    restore_window_size(outer, ui_preferences, "main_dialog_size", (1080, 760))
    outer_layout = qt_widgets.QVBoxLayout(outer)
    tabs = qt_widgets.QTabWidget()
    scope_page = qt_widgets.QWidget()
    config_page = qt_widgets.QWidget()
    scope_dialog = _ScopeDialog(
        qt_widgets,
        inventory,
        selected_ids,
        language,
        translator,
        ignored_non_xhtml=ignored_non_xhtml,
        spine_ids=spine_ids,
        nav_id=nav_id,
        recovery_notices=notice,
        initial_scope=initial_scope,
        embedded=True,
        container=scope_page,
        parent_dialog=outer,
    )
    config_dialog = _ConversionConfigDialog(
        qt_widgets, configs, default_config, jieba_configs, translator=translator,
        jieba_probe=jieba_probe, initial_options=initial_options,
        metadata_available=metadata_available,
        services=services, ui_preferences=ui_preferences,
        embedded=True, container=config_page, parent_dialog=outer,
    )
    tabs.addTab(scope_page, translator.text("scope.title"))
    tabs.addTab(config_page, translator.text("config.title"))
    language_corner = qt_widgets.QWidget()
    language_corner_layout = qt_widgets.QHBoxLayout(language_corner)
    language_corner_layout.setContentsMargins(0, 0, 0, 0)
    language_corner_layout.addWidget(scope_dialog.language_label)
    language_corner_layout.addWidget(scope_dialog.language_combo)
    tabs.setCornerWidget(language_corner, _enum_value(qt_widgets.Qt, "TopRightCorner"))
    summary = qt_widgets.QLabel()
    summary.setWordWrap(True)
    outer_layout.addWidget(summary)
    direction_row = qt_widgets.QHBoxLayout()
    direction_row.addWidget(config_dialog.direction_label)
    direction_row.addWidget(config_dialog.combo, 1)
    direction_row.addStretch(1)
    outer_layout.addLayout(direction_row)
    outer_layout.addWidget(tabs)
    footer = qt_widgets.QHBoxLayout()
    cancel_button = qt_widgets.QPushButton(translator.text("common.cancel"))
    analyze_button = qt_widgets.QPushButton(translator.text("config.continue"))
    analyze_button.setDefault(True)

    def update_analyze_enabled():
        selected_ids = scope_dialog.selected_ids()
        data = run_summary_data(
            selected_ids, nav_id, config_dialog._get_config(),
            {**config_dialog.options_panel.preference_values(),
             "metadata_available": config_dialog.options_panel._metadata_available},
        )
        direction = configuration_label(translator, data["config"])
        summary_text = translator.text(
            "scope.run_summary", files=data["file_count"], direction=direction)
        details = []
        if not data["file_count"]:
            details.append(translator.text("scope.run_summary_empty"))
        if data["nav_included"]:
            details.append(translator.text("scope.run_summary_nav_included"))
        elif not data["nav_available"]:
            details.append(translator.text("scope.run_summary_nav_unavailable"))
        details.extend(translator.text(
            f"scope.run_summary_{name}" if name in {"ncx", "metadata"}
            else "scope.run_summary_metadata_unavailable")
                       for name in data["additions"])
        if data["risks"]:
            risk_names = {
                "pivot": "scope.run_summary_risk_pivot",
                "pivot_inactive": "scope.run_summary_risk_pivot_inactive",
                "metadata": "scope.run_summary_risk_metadata",
                "metadata_inactive": "scope.run_summary_risk_metadata_inactive",
            }
            details.append(translator.text("scope.run_summary_risks", items=" · ".join(
                translator.text(risk_names[name]) for name in data["risks"])))
        if details:
            summary_text += "\n" + " · ".join(details)
        summary.setText(summary_text)
        summary.setToolTip(summary_text)
        metrics = getattr(summary, "fontMetrics", None)
        metrics = metrics() if callable(metrics) else None
        line_height = getattr(metrics, "lineSpacing", None)
        if callable(line_height):
            summary.setMaximumHeight(line_height() * 2 + 8)
        analyze_button.setEnabled(
            scope_dialog._selection_is_valid() and config_dialog._continue_is_allowed())

    scope_dialog._analysis_enabled_callback = update_analyze_enabled
    config_dialog._completion_enabled_callback = update_analyze_enabled
    config_dialog.options_panel._summary_changed_callback = update_analyze_enabled
    update_analyze_enabled()
    footer.addStretch(1)
    footer.addWidget(cancel_button)
    footer.addWidget(analyze_button)
    outer_layout.addLayout(footer)

    def retranslate_combined_controls():
        tabs.setTabText(0, translator.text("scope.title"))
        tabs.setTabText(1, translator.text("config.title"))
        cancel_button.setText(translator.text("common.cancel"))
        analyze_button.setText(translator.text("config.continue"))
        config_dialog._retranslate()

    scope_dialog._language_changed_callback = retranslate_combined_controls
    cancel_button.clicked.connect(outer.reject)
    cancel_button.clicked.connect(config_dialog._stop_probe_timer)

    def accept_combined():
        scope_dialog._accept(close=False)
        if not scope_dialog.accepted:
            return
        config_dialog._accept(close=False)
        if not config_dialog.accepted:
            return
        outer.accept()

    analyze_button.clicked.connect(accept_combined)
    exec_dialog(outer)
    config_dialog._stop_probe_timer()
    if callable(save_ui_preferences):
        state = {**dict(ui_preferences or {}), **config_dialog.options_panel.ui_state()}
        size = getattr(outer, "size", None)
        size = size() if callable(size) else None
        if size is not None:
            width, height = getattr(size, "width", None), getattr(size, "height", None)
            if callable(width) and callable(height):
                state["main_dialog_size"] = [int(width()), int(height())]
        save_ui_preferences(state)
    if not config_dialog.accepted or not scope_dialog.accepted:
        return ScopeOutcome(False, None, scope_dialog.language)
    translator.set_language(scope_dialog.language)
    selection = scope_dialog.selection
    return ScopeOutcome(
        True, selection, scope_dialog.language, config_dialog.selected_config,
    )


def create_progress_reporter(
    total: int, parent: Any = None, *, translator: Translator | None = None,
    ui_preferences=None, save_ui_preferences=None,
) -> ProgressReporter:
    """Create a progress reporter using Sigil's already available Qt runtime."""

    translator = translator or Translator("en")
    qt_widgets = _load_ui_qt(translator)
    ensure_application(qt_widgets, language=translator.language)
    return ProgressReporter(
        qt_widgets, total, parent, translator,
        ui_preferences=ui_preferences,
        save_ui_preferences=save_ui_preferences,
    )


def _show_diagnostics_dialog(
    qt: Any, planned_documents: Sequence[PlannedDocument], translator: Translator,
) -> None:
    records = _diagnostic_records(planned_documents, translator)
    if not records:
        return
    dialog = qt.QDialog()
    dialog.setWindowTitle(plugin_window_title(
        translator, translator.text("preview.diagnostics_title")))
    resize = getattr(dialog, "resize", None)
    if callable(resize):
        resize(850, 520)
    layout = qt.QVBoxLayout(dialog)
    panel = _DiagnosticPanel(qt, records, translator)
    panel.set_expanded(True)
    layout.addWidget(panel.widget, 1)
    buttons = qt.QHBoxLayout()
    buttons.addStretch(1)
    close = qt.QPushButton(translator.text("common.close"))
    buttons.addWidget(close)
    layout.addLayout(buttons)
    close.clicked.connect(dialog.accept)
    exec_dialog(dialog)


def show_preview(
    planned: Sequence[PlannedDocument], *, translator: Translator | None = None,
    services: Any = None, ui_preferences=None, save_ui_preferences=None,
) -> PreviewOutcome:
    """Show a preview and return the sessions containing user decisions."""

    translator = translator or Translator("en")
    qt_widgets = _load_ui_qt(translator)
    previews = tuple(PreviewSession(item.plan) for item in planned)
    ensure_application(qt_widgets, language=translator.language)
    dialog = _PreviewDialog(
        qt_widgets, planned, previews, translator, services,
        ui_preferences=ui_preferences,
    )
    exec_dialog(dialog.dialog)
    if callable(save_ui_preferences):
        state = dict(dialog._ui_preferences)
        size = dialog.dialog.size()
        width = getattr(size, "width", None)
        height = getattr(size, "height", None)
        if callable(width) and callable(height) and width() > 0 and height() > 0:
            state["preview_dialog_size"] = [int(width()), int(height())]
        splitter_sizes = dialog.splitter.sizes()
        if (
            isinstance(splitter_sizes, (tuple, list))
            and len(splitter_sizes) == 2
            and all(isinstance(item, int) and not isinstance(item, bool) and item >= 0
                    for item in splitter_sizes)
            and any(splitter_sizes)
        ):
            state["preview_splitter_sizes"] = [int(item) for item in splitter_sizes]
        save_ui_preferences(state)
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
    files_all_skipped: int = 0,
    failed_file: str | None = None,
    return_to_scope: bool = False,
    diagnostics=(),
    diagnostic_documents: Sequence[PlannedDocument] = (),
    report_text: str | None = None,
    translator: Translator | None = None,
    ui_preferences=None,
    save_ui_preferences=None,
) -> str | None:
    """Show a concise localized terminal result after the write boundary."""

    translator = translator or Translator("en")
    qt_widgets = _load_ui_qt(translator)
    ensure_application(qt_widgets, language=translator.language)
    not_written = (
        max(files_scanned - files_changed, 0)
        if files_not_written is None
        else max(int(files_not_written), 0)
    )
    rows = [translator.text("result.row.scanned", count=max(int(files_scanned), 0))]
    if files_changed > 0:
        written_key = (
            "result.row.written" if skipped_changes > 0
            else "result.row.written_accepted")
        written_values = {
            "files": max(int(files_changed), 0),
            "accepted": max(int(accepted_changes), 0),
        }
        if written_key == "result.row.written":
            written_values["skipped"] = max(int(skipped_changes), 0)
        rows.append(translator.text(written_key, **written_values))
    if not_written > 0:
        unwritten_key = (
            "result.row.unwritten" if files_without_changes > 0
            else "result.row.unwritten_plain")
        unwritten_values = {"files": not_written}
        if unwritten_key == "result.row.unwritten":
            unwritten_values["unchanged"] = max(int(files_without_changes), 0)
        rows.append(translator.text(unwritten_key, **unwritten_values))
    all_skipped = max(int(files_all_skipped), 0)
    if all_skipped > 0:
        rows.append(translator.text(
            "result.files_all_skipped", count=all_skipped))
    cancelled = status == "cancelled"
    if status == "partial_failure":
        status_line = translator.text("result.status.partial", file=failed_file or "?")
        method = qt_widgets.QMessageBox.warning
    elif status == "cancelled":
        status_line = translator.text("result.status.cancelled_unchanged")
        method = qt_widgets.QMessageBox.information
    elif accepted_changes == 0 and skipped_changes:
        status_line = translator.text("result.status.skipped")
        method = qt_widgets.QMessageBox.information
    elif accepted_changes == 0:
        status_line = translator.text("result.status.noop")
        method = qt_widgets.QMessageBox.information
    else:
        status_line = translator.text("result.status.success")
        method = qt_widgets.QMessageBox.information
    message = status_line if cancelled else status_line + "\n\n" + "\n".join(rows)
    if status == "success" and accepted_changes > 0:
        message += "\n\n" + translator.text("result.save_reminder")
    diagnostics = tuple(diagnostics)
    diagnostic_documents = tuple(diagnostic_documents)
    diagnostic_records = _diagnostic_records(diagnostic_documents, translator)
    if diagnostics and not cancelled:
        rows = []
        for item in diagnostics:
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                file_name, code = item[:2]
                row = (
                    f"{file_name}{translator.text('common.label_separator')}"
                    f"{diagnostic_summary(translator, str(code))}"
                )
                rows.append(row)
            else:
                rows.append(str(item))
        message += "\n\n" + translator.text("result.invalid_sources") + "\n" + "\n".join(rows)
    if return_to_scope or report_text or diagnostic_records:
        box = qt_widgets.QMessageBox()
        box.setWindowTitle(plugin_window_title(
            translator, translator.text("result.title")))
        box.setText(message)
        back = None
        if return_to_scope:
            back = box.addButton(
                translator.text("result.back_to_scope"), qt_widgets.QMessageBox.ActionRole)
        view_report = None
        if report_text:
            view_report = box.addButton(
                translator.text("result.view_report"), qt_widgets.QMessageBox.ActionRole)
        view_diagnostics = None
        if diagnostic_records:
            view_diagnostics = box.addButton(
                translator.text("result.view_diagnostics"),
                qt_widgets.QMessageBox.ActionRole,
            )
        close = box.addButton(translator.text("common.close"), qt_widgets.QMessageBox.AcceptRole)
        box.setDefaultButton(close)
        box.setEscapeButton(close)
        while True:
            exec_dialog(box)
            clicked = box.clickedButton()
            if view_report is not None and clicked is view_report:
                _show_report_text(
                    qt_widgets, report_text, translator,
                    ui_preferences=ui_preferences,
                    save_ui_preferences=save_ui_preferences,
                )
                continue
            if view_diagnostics is not None and clicked is view_diagnostics:
                _show_diagnostics_dialog(
                    qt_widgets, diagnostic_documents, translator)
                continue
            return "back_to_scope" if back is not None and clicked is back else "close"
    method(None, plugin_window_title(
        translator, translator.text("result.title")), message)
    return None


def _show_report_text(
    qt_widgets, report_text: str, translator: Translator, *,
    ui_preferences=None, save_ui_preferences=None,
) -> None:
    dialog = qt_widgets.QDialog()
    dialog.setWindowTitle(plugin_window_title(
        translator, translator.text("result.view_report")))
    restore_window_size(
        dialog, ui_preferences, "result_report_dialog_size", (760, 560))
    layout = qt_widgets.QVBoxLayout(dialog)
    view = qt_widgets.QPlainTextEdit()
    view.setReadOnly(True)
    view.setPlainText(report_text)
    layout.addWidget(view)
    close = qt_widgets.QPushButton(translator.text("common.close"))
    close.clicked.connect(dialog.accept)
    layout.addWidget(close)
    exec_dialog(dialog)
    save_window_size(dialog, "result_report_dialog_size", save_ui_preferences)


def show_error(
    *,
    kind: str,
    detail: str,
    files_written: int,
    log_path: str,
    affected_files=(),
    translator: Translator | None = None,
    summary: str | None = None,
) -> None:
    """Show a privacy-safe failure summary and copyable diagnostic context."""

    translator = translator or Translator("en")
    qt_widgets = _load_ui_qt(translator)
    ensure_application(qt_widgets, language=translator.language)
    dialog = qt_widgets.QDialog()
    dialog.setWindowTitle(plugin_window_title(
        translator, translator.text("error.title")))
    dialog.setMinimumWidth(420)
    layout = qt_widgets.QVBoxLayout(dialog)
    message_key = {
        "VERIFY_FAILED": "error.verify_failed",
        "SOURCE_CHANGED": "error.source_changed",
        "SETTINGS_CHANGED": "error.settings_changed",
        "GROUP_PARTIAL": "error.group_partial",
    }.get(kind, "error.unexpected")
    message = qt_widgets.QLabel(summary if summary is not None else translator.text(message_key))
    message.setWordWrap(True)
    message_row = qt_widgets.QHBoxLayout()
    icon_label = qt_widgets.QLabel()
    style_type = getattr(qt_widgets.QStyle, "StandardPixmap", qt_widgets.QStyle)
    warning_type = style_type.SP_MessageBoxWarning
    warning_icon = dialog.style().standardIcon(warning_type)
    icon_label.setPixmap(warning_icon.pixmap(24, 24))
    message_row.addWidget(icon_label)
    message_row.addWidget(message, 1)
    layout.addLayout(message_row)
    write_key = "error.no_files_written" if not files_written else "error.some_files_written"
    write_status = qt_widgets.QLabel(
        translator.text(write_key, count=max(int(files_written), 0)))
    write_status.setWordWrap(True)
    layout.addWidget(write_status)
    next_step = qt_widgets.QLabel(translator.text("error.next_step"))
    next_step.setWordWrap(True)
    layout.addWidget(next_step)

    lines = [
        translator.text("error.code_line", code=kind),
        translator.text("error.type_line", detail=detail),
    ]
    for href, codes in affected_files:
        lines.append(translator.text("error.file_line", file=href))
        if codes:
            lines.append(translator.text("error.diagnostics_line", codes=", ".join(codes)))
    lines.append(translator.text("error.log_line", path=log_path))
    diagnostic = "\n".join(lines)

    details_button = qt_widgets.QPushButton(translator.text("error.details"))
    details_button.setAutoDefault(False)
    details = qt_widgets.QPlainTextEdit()
    details.setReadOnly(True)
    details.setPlainText(diagnostic)
    details.setVisible(False)
    details_button.clicked.connect(lambda: details.setVisible(not details.isVisible()))
    layout.addWidget(details_button)
    layout.addWidget(details)

    buttons = qt_widgets.QHBoxLayout()
    copy_button = qt_widgets.QPushButton(translator.text("error.copy_diagnostics"))
    close_button = qt_widgets.QPushButton(translator.text("common.close"))
    copy_button.setAutoDefault(False)
    close_button.setAutoDefault(False)
    close_button.setDefault(True)
    copy_button.clicked.connect(lambda: qt_widgets.QApplication.clipboard().setText(diagnostic))
    close_button.clicked.connect(dialog.accept)
    buttons.addWidget(copy_button)
    buttons.addWidget(close_button)
    layout.addLayout(buttons)
    exec_dialog(dialog)


def _guarded_preview_dialog(qt_widgets, guard):
    base_dialog = qt_widgets.QDialog

    class GuardedPreviewDialog(base_dialog):
        def reject(self):
            if guard():
                super().reject()

    return GuardedPreviewDialog()


_MAX_DECISION_HISTORY_OPERATIONS = 100
_MAX_DECISION_HISTORY_CHANGES = 2_000_000


class _PreviewDialog:
    def __init__(
        self, qt_widgets: Any, planned, previews: tuple[PreviewSession, ...],
        translator: Translator, services: Any = None, *, ui_preferences=None,
    ) -> None:
        self._qt = qt_widgets
        self._translator = translator
        self._services = services
        self._ui_preferences = dict(ui_preferences or {})
        self._planned = planned
        self._previews = previews
        # Plans are immutable, so the preview rows never change identity.  A
        # cached change object avoids doing a linear ``next(...)`` lookup for
        # every row every time a bulk decision refreshes the list.
        preview_changes = tuple((preview, preview.changes) for preview in previews)
        self._entries: tuple[tuple[PreviewSession, TokenChange], ...] = tuple(
            (preview, change)
            for preview, changes in preview_changes
            for change in changes
        )
        self._entry_position = {
            (change.file_id, change.change_id): index
            for index, (_preview, change) in enumerate(self._entries)
        }
        self._href_by_id = {
            item.source.file_id: item.source.href for item in self._planned
        }
        self._source_by_id = {
            item.source.file_id: item.source.source
            for item in self._planned
            if isinstance(getattr(item.source, "source", None), str)
        }
        self._diagnostic_records = None
        self._diagnostic_count = _diagnostic_record_count(self._planned)
        self._has_diagnostics = self._diagnostic_count > 0
        self._targets_by_id = {
            (item.source.file_id, target.node_id): target
            for item in self._planned
            for target in getattr(item.plan, "targets", ())
        }
        self._kind_by_id = {
            item.source.file_id: item.source.document_kind for item in self._planned
        }
        self._file_order = {
            item.source.file_id: index for index, item in enumerate(self._planned)
        }
        group_entries = {}
        entries_by_group = {}
        entries_by_file = {}
        for entry in self._entries:
            _preview, change = entry
            entries_by_file.setdefault(change.file_id, []).append(entry)
            if change.group_id:
                count, files = group_entries.get(change.group_id, (0, set()))
                files.add(change.file_id)
                group_entries[change.group_id] = (count + 1, files)
                entries_by_group.setdefault(change.group_id, []).append(entry)
        self._group_entries_by_id = {
            group_id: tuple(entries) for group_id, entries in entries_by_group.items()
        }
        self._entries_by_file = {
            file_id: tuple(entries) for file_id, entries in entries_by_file.items()
        }
        self._group_file_ids = {
            group_id: frozenset(files)
            for group_id, (_count, files) in group_entries.items()
        }
        self._group_stats = {
            group_id: (count, len(files))
            for group_id, (count, files) in group_entries.items()
        }
        self._preview_by_file_id = {}
        self._initial_file_change_counts = {}
        self._one_file_per_preview = True
        for preview, changes in preview_changes:
            file_ids = dict.fromkeys(change.file_id for change in changes)
            for file_id in file_ids:
                self._preview_by_file_id.setdefault(file_id, preview)
            if len(file_ids) > 1:
                self._one_file_per_preview = False
            elif file_ids:
                file_id = next(iter(file_ids))
                self._initial_file_change_counts[file_id] = (
                    self._initial_file_change_counts.get(file_id, 0) + len(changes)
                )
        del preview_changes
        self._undo_stack = []
        self._redo_stack = []
        self._history_sequence = 0
        self._history_record_count = 0
        self._history_feedback = ""
        self._recompute_counts()
        self._last_group_feedback = ""
        self._visible_entries_cache = self._entries
        self._visible_positions = list(range(len(self._entries)))
        self.applied = False
        self.back_to_settings = False
        self.checkpoint_notice_shown = False
        self._allow_reject = False

        self.dialog = _guarded_preview_dialog(qt_widgets, self._guard_reject)
        self.dialog.setWindowTitle(plugin_window_title(
            self._translator, self._translator.text("preview.title")))
        restore_window_size(
            self.dialog, self._ui_preferences, "preview_dialog_size", (900, 620))
        self._build()
        self._refresh()
        self.table_view.setFocus()

    def _ensure_diagnostics_panel(self, index=None) -> None:
        """Build the secondary diagnostics view only when the user opens it."""

        tab_index = self._diagnostic_tab_index
        if tab_index is None or (index is not None and index != tab_index):
            return
        if self.diagnostic_panel is not None:
            return
        records = _diagnostic_records(self._planned, self._translator)
        self._diagnostic_records = records
        if not records:
            self.detail_tabs.removeTab(tab_index)
            self._diagnostic_tab_index = None
            return
        self.diagnostic_panel = _DiagnosticPanel(
            self._qt, records, self._translator,
            on_related_change=self._navigate_to_related_change,
        )
        self._diagnostic_tab_layout.addWidget(self.diagnostic_panel.widget)
        self.detail_tabs.setTabText(
            tab_index,
            self._translator.text("preview.diagnostics_count", count=len(records)),
        )

    def _build(self) -> None:
        qt = self._qt
        layout = qt.QVBoxLayout(self.dialog)

        self.summary = qt.QLabel()
        layout.addWidget(self.summary)
        filter_row = qt.QHBoxLayout()
        self.file_filter = qt.QComboBox()
        self.category_filter = qt.QComboBox()
        self.risk_filter = qt.QComboBox()
        self.source_filter = qt.QComboBox()
        self.status_filter = qt.QComboBox()
        file_counts = self._file_filter_counts
        ordered_ids = sorted(
            file_counts,
            key=lambda file_id: (
                self._file_order.get(file_id, len(self._file_order)),
                self._href_by_id.get(file_id, file_id),
            ),
        )
        file_values = [
            (
                self._translator.text(
                    "preview.filter_file_option",
                    href=(
                        self._translator.text("preview.file.metadata")
                        if self._kind_by_id.get(file_id) == "metadata"
                        else self._href_by_id.get(file_id, file_id)
                    ),
                    changes=file_counts[file_id][0],
                    undecided=file_counts[file_id][1],
                ),
                file_id,
            )
            for file_id in ordered_ids
        ]
        category_values = [
            (
                self._translator.text(f"preview.category_value.{category}"),
                category,
            )
            for category in sorted({change.category for _, change in self._entries})
        ]
        risk_values = [
            (
                self._translator.text(f"preview.risk_value.{risk.lower()}"),
                risk,
            )
            for risk in ("LOW", "REVIEW", "HIGH")
            if any(change.risk == risk for _, change in self._entries)
        ]
        source_values = [
            (self._source_filter_label(source), source)
            for source in sorted({change.rule_source for _, change in self._entries
                                  if change.rule_source})
        ]
        status_values = [
            (self._translator.text(f"preview.filter_status.{status}"), status)
            for status in ("undecided", "accepted", "rejected")
        ]
        self._populate_filter(self.file_filter, self._translator.text("preview.filter_file"),
                              file_values, self._translator)
        self._populate_filter(self.category_filter, self._translator.text("preview.filter_category"),
                              category_values, self._translator)
        self._populate_filter(self.risk_filter, self._translator.text("preview.filter_risk"),
                              risk_values, self._translator)
        self._populate_filter(self.source_filter, self._translator.text("preview.filter_source"),
                              source_values, self._translator)
        self._populate_filter(self.status_filter, self._translator.text("preview.filter_status"),
                              status_values, self._translator)
        adjust_policy = _enum_value(
            qt.QComboBox, "AdjustToMinimumContentsLengthWithIcon")
        for widget in (self.file_filter, self.category_filter, self.risk_filter,
                       self.source_filter, self.status_filter):
            if adjust_policy is not None:
                set_adjust_policy = getattr(widget, "setSizeAdjustPolicy", None)
                if callable(set_adjust_policy):
                    set_adjust_policy(adjust_policy)
            set_minimum_length = getattr(widget, "setMinimumContentsLength", None)
            if callable(set_minimum_length):
                set_minimum_length(10)
            widget.currentIndexChanged.connect(lambda *_args: self._refresh())
        for widget, key in (
            (self.file_filter, "a11y.preview.file_filter"),
            (self.category_filter, "a11y.preview.category_filter"),
            (self.risk_filter, "a11y.preview.risk_filter"),
            (self.source_filter, "a11y.preview.source_filter"),
        ):
            widget.setAccessibleName(self._translator.text(key))
        layout.addLayout(filter_row)

        search_row = qt.QHBoxLayout()
        search_row.addWidget(self.status_filter)
        self.status_filter.setAccessibleName(
            self._translator.text("a11y.preview.status_filter"))
        self.search_input = qt.QLineEdit()
        self.search_input.setPlaceholderText(self._translator.text("preview.filter_search"))
        self.search_input.setAccessibleName(self._translator.text("a11y.preview.search"))
        search_row.addWidget(self.search_input, 1)
        self.clear_filters_button = qt.QPushButton(
            self._translator.text("preview.clear_filters"))
        self.clear_filters_button.setAccessibleName(
            self._translator.text("a11y.preview.clear_filters"))
        search_row.addWidget(self.clear_filters_button)
        self.more_filters_button = qt.QToolButton()
        self.more_filters_button.setText(
            self._translator.text("preview.more_filters", count=0))
        self.more_filters_button.setCheckable(True)
        search_row.addWidget(self.more_filters_button)
        self.filter_count_label = qt.QLabel()
        search_row.addWidget(self.filter_count_label)
        layout.addLayout(search_row)
        self.extra_filters = qt.QWidget()
        extra_filter_layout = qt.QHBoxLayout(self.extra_filters)
        for widget in (self.file_filter, self.category_filter,
                       self.risk_filter, self.source_filter):
            extra_filter_layout.addWidget(widget)
        layout.addWidget(self.extra_filters)
        self.extra_filters.setVisible(False)
        self.more_filters_button.toggled.connect(self.extra_filters.setVisible)
        self.status_filter.currentIndexChanged.connect(lambda *_args: self._refresh())
        self.clear_filters_button.clicked.connect(self._clear_filters)
        self.search_input.textChanged.connect(self._schedule_filter_refresh)
        timer_type = getattr(qt, "QTimer", None)
        self._search_refresh_timer = timer_type(self.dialog) if callable(timer_type) else None
        if self._search_refresh_timer is not None:
            set_single_shot = getattr(self._search_refresh_timer, "setSingleShot", None)
            if callable(set_single_shot):
                set_single_shot(True)
            self._search_refresh_timer.setInterval(140)
            self._search_refresh_timer.timeout.connect(self._refresh)

        self.table_view = qt.QTableView()
        self.table_model = _create_preview_table_model(
            qt, self._entries, self._href_by_id, self._group_stats, self._translator,
            self._targets_by_id)(self.table_view)
        self.table_view.setModel(self.table_model)
        item_view = qt.QAbstractItemView
        self.table_view.setSelectionBehavior(_enum_value(item_view, "SelectRows"))
        self.table_view.setSelectionMode(_enum_value(item_view, "SingleSelection"))
        self.table_view.selectionModel().currentRowChanged.connect(
            lambda current, _previous: self._show_current(current.row()))
        header = self.table_view.horizontalHeader()
        interactive = _enum_value(qt.QHeaderView, "Interactive")
        stretch = _enum_value(qt.QHeaderView, "Stretch")
        header.setStretchLastSection(False)
        if interactive is not None:
            for column in range(7):
                mode = stretch if column in {3, 4} else interactive
                if mode is not None:
                    header.setSectionResizeMode(column, mode)
        self.table_view.setColumnHidden(2, True)
        set_precision = getattr(header, "setResizeContentsPrecision", None)
        if callable(set_precision):
            set_precision(50)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setAccessibleName(
            self._translator.text("a11y.preview.changes_table"))
        set_column_width = getattr(self.table_view, "setColumnWidth", None)
        if callable(set_column_width):
            for column, width in enumerate((84, 96, 64, 142, 142, 126, 64)):
                set_column_width(column, width)

        self.show_source_context = qt.QCheckBox(
            self._translator.text("preview.show_source_context"))
        self.show_source_context.toggled.connect(self._refresh_current)
        self.detail_panel = qt.QWidget()
        detail_layout = qt.QVBoxLayout(self.detail_panel)
        detail_layout.addWidget(self.show_source_context)

        self.detail = qt.QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMinimumHeight(48)
        detail_layout.addWidget(self.detail)
        comparison = qt.QWidget()
        comparison_layout = qt.QHBoxLayout(comparison)
        self.source_detail = qt.QPlainTextEdit()
        self.target_detail = qt.QPlainTextEdit()
        for editor in (self.source_detail, self.target_detail):
            editor.setReadOnly(True)
            editor.setMinimumHeight(64)
        self.source_detail.setAccessibleName(self._translator.text("preview.before"))
        self.target_detail.setAccessibleName(self._translator.text("preview.after"))
        source_column = qt.QVBoxLayout()
        source_column.addWidget(qt.QLabel(self._translator.text("preview.before")))
        source_column.addWidget(self.source_detail, 1)
        target_column = qt.QVBoxLayout()
        target_column.addWidget(qt.QLabel(self._translator.text("preview.after")))
        target_column.addWidget(self.target_detail, 1)
        comparison_layout.addLayout(source_column, 1)
        comparison_layout.addLayout(target_column, 1)
        detail_layout.addWidget(comparison, 1)

        self.detail_tabs = qt.QTabWidget()
        self.detail_tabs.addTab(
            self.detail_panel, self._translator.text("preview.current_item"))
        self.splitter = qt.QSplitter(_enum_value(qt.Qt, "Vertical"))
        self.splitter.addWidget(self.table_view)
        self.splitter.addWidget(self.detail_tabs)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        saved_splitter_sizes = self._ui_preferences.get("preview_splitter_sizes")
        if (
            isinstance(saved_splitter_sizes, (tuple, list))
            and len(saved_splitter_sizes) == 2
            and all(isinstance(item, int) and not isinstance(item, bool) and item >= 0
                    for item in saved_splitter_sizes)
            and any(saved_splitter_sizes)
        ):
            self.splitter.setSizes([int(item) for item in saved_splitter_sizes])
        layout.addWidget(self.splitter, 1)

        self.diagnostic_panel = None
        self._diagnostic_tab_index = None
        self._diagnostic_tab_layout = None
        if self._has_diagnostics:
            diagnostic_tab = qt.QWidget()
            self._diagnostic_tab_layout = qt.QVBoxLayout(diagnostic_tab)
            self._diagnostic_tab_index = self.detail_tabs.addTab(
                diagnostic_tab, self._translator.text(
                    "preview.diagnostics_count", count=self._diagnostic_count))
            if self._diagnostic_tab_index is None:
                self._diagnostic_tab_index = 1
            tab_changed = getattr(self.detail_tabs, "currentChanged", None)
            if callable(getattr(tab_changed, "connect", None)):
                tab_changed.connect(self._ensure_diagnostics_panel)

        buttons = qt.QHBoxLayout()
        self.accept_this_button = qt.QPushButton(self._translator.text("preview.accept_this"))
        self.reject_this_button = qt.QPushButton(self._translator.text("preview.skip_this"))
        self.next_undecided_button = qt.QPushButton(
            self._translator.text("preview.next_undecided"))
        self.accept_this_button.setToolTip(
            self._translator.text("preview.shortcut.accept_this"))
        self.reject_this_button.setToolTip(
            self._translator.text("preview.shortcut.skip_this"))
        self.next_undecided_button.setToolTip(
            self._translator.text("preview.shortcut.next_undecided"))
        self.undo_button = qt.QPushButton(self._translator.text("preview.undo"))
        self.redo_button = qt.QPushButton(self._translator.text("preview.redo"))
        self.reset_current_button = qt.QPushButton(
            self._translator.text("preview.reset_current"))
        self.undo_button.setToolTip(self._translator.text("preview.undo_tooltip"))
        self.redo_button.setToolTip(self._translator.text("preview.redo_tooltip"))
        self.reset_current_button.setToolTip(
            self._translator.text("preview.reset_current_tooltip"))
        self.undo_button.setAccessibleName(self._translator.text("a11y.preview.undo"))
        self.redo_button.setAccessibleName(self._translator.text("a11y.preview.redo"))
        self.reset_current_button.setAccessibleName(
            self._translator.text("a11y.preview.reset_current"))
        self.export_button = qt.QPushButton(self._translator.text("preview.export"))
        self.batch_button = qt.QPushButton(self._translator.text("preview.batch_decide"))
        self.batch_button.setVisible(False)
        self.apply_button = qt.QPushButton(self._translator.text("preview.apply"))
        self.apply_status_label = qt.QLabel()
        self.back_settings_button = qt.QPushButton(self._translator.text("preview.back_settings"))
        self.cancel_button = qt.QPushButton(self._translator.text("common.cancel"))
        for button in (self.accept_this_button, self.reject_this_button,
                       self.next_undecided_button, self.undo_button, self.redo_button):
            buttons.addWidget(button)
        self.more_button = qt.QToolButton()
        self.more_button.setText(self._translator.text("preview.more_actions"))
        self.more_menu = qt.QMenu(self.more_button)
        self.more_button.setMenu(self.more_menu)
        popup_mode = _enum_value(qt.QToolButton, "InstantPopup")
        if popup_mode is not None:
            self.more_button.setPopupMode(popup_mode)
        action_type = getattr(getattr(qt, "QtGui", None), "QAction", None)
        action_type = action_type or getattr(qt, "QAction", None)
        self._more_actions = []
        self._more_action_by_button = {}
        for button in (self.reset_current_button, self.export_button, self.batch_button):
            button.setVisible(False)
            if action_type is not None:
                action = action_type(button.text(), self.more_menu)
                action.triggered.connect(lambda _checked=False, target=button: target.click())
                action.setEnabled(button.isEnabled())
                self.more_menu.addAction(action)
                self._more_actions.append(action)
                self._more_action_by_button[button] = action
        buttons.addWidget(self.more_button)
        layout.addLayout(buttons)
        actions = qt.QHBoxLayout()
        actions.addWidget(self.apply_status_label)
        self.resolve_remaining_button = qt.QPushButton(
            self._translator.text("preview.resolve_remaining", count=0))
        self.resolve_remaining_button.setVisible(False)
        self.resolve_remaining_button.clicked.connect(
            lambda: self._open_batch_decision(initial_scope="all"))
        actions.addWidget(self.resolve_remaining_button)
        actions.addStretch(1)
        for button in (self.back_settings_button, self.cancel_button, self.apply_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        self._disable_default_buttons()

        self.accept_this_button.clicked.connect(self._accept_this)
        self.reject_this_button.clicked.connect(self._reject_this)
        self.next_undecided_button.clicked.connect(self._next_undecided)
        self.undo_button.clicked.connect(self._undo_preview_action)
        self.redo_button.clicked.connect(self._redo_preview_action)
        self.reset_current_button.clicked.connect(self._reset_current_to_undecided)
        self.export_button.clicked.connect(self._export_preview)
        self.batch_button.clicked.connect(
            lambda: self._open_batch_decision(initial_scope="filtered"))
        self.apply_button.clicked.connect(self._apply)
        self.back_settings_button.clicked.connect(self._back_to_settings)
        self.cancel_button.clicked.connect(self.dialog.reject)
        self.export_button.setEnabled(getattr(self._services, "export_preview", None) is not None)
        export_action = self._more_action_by_button.get(self.export_button)
        if export_action is not None:
            export_action.setEnabled(self.export_button.isEnabled())
        self._bind_shortcuts()

    def _disable_default_buttons(self) -> None:
        button_type = getattr(self._qt, "QPushButton", None)
        find_children = getattr(self.dialog, "findChildren", None)
        buttons = ()
        if callable(button_type) and callable(find_children):
            try:
                buttons = find_children(button_type) or ()
            except TypeError:
                buttons = ()
        if not buttons:
            buttons = tuple(
                getattr(self, name, None)
                for name in (
                    "accept_this_button", "reject_this_button", "next_undecided_button",
                    "undo_button",
                    "redo_button", "reset_current_button", "export_button",
                    "resolve_remaining_button", "apply_button", "back_settings_button",
                    "cancel_button",
                )
            )
        for button in buttons:
            if button is None:
                continue
            set_auto_default = getattr(button, "setAutoDefault", None)
            if callable(set_auto_default):
                set_auto_default(False)
            set_default = getattr(button, "setDefault", None)
            if callable(set_default):
                set_default(False)

    def _bind_shortcuts(self) -> None:
        shortcut_type = getattr(self._qt, "QShortcut", None)
        key_sequence = getattr(self._qt, "QKeySequence", None)
        if shortcut_type is None:
            gui = getattr(self._qt, "QtGui", None)
            shortcut_type = getattr(gui, "QShortcut", None)
            key_sequence = key_sequence or getattr(gui, "QKeySequence", None)
        if shortcut_type is None or key_sequence is None:
            return
        # Keep decision shortcuts inside the table subtree. Search and detail
        # editors retain native typing and undo/redo commands.
        context = _enum_value(getattr(self._qt, "Qt", None), "WidgetWithChildrenShortcut")
        if context is None:
            return
        self._shortcuts = []
        for sequence, callback in (
            ("A", self._accept_this),
            ("S", self._reject_this),
            ("N", self._next_undecided),
            ("Shift+N", self._previous_undecided),
        ):
            shortcut = shortcut_type(key_sequence(sequence), self.table_view)
            shortcut.setContext(context)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)
        standard_keys = getattr(key_sequence, "StandardKey", None)
        for name, fallback, callback in (
            ("Undo", "Ctrl+Z", self._undo_preview_action),
            ("Redo", "Ctrl+Shift+Z", self._redo_preview_action),
        ):
            standard = getattr(standard_keys, name, None)
            if standard is None:
                standard = getattr(key_sequence, name, None)
            sequence = key_sequence(standard if standard is not None else fallback)
            shortcut = shortcut_type(sequence, self.table_view)
            shortcut.setContext(context)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)

    def _export_preview(self) -> None:
        export = (
            getattr(self._services, "export_preview", None)
            if self._services is not None else None
        )
        if export is None:
            return
        dialog = self._qt.QDialog(self.dialog)
        dialog.setWindowTitle(self._translator.text("preview.export_options_title"))
        layout = self._qt.QVBoxLayout(dialog)
        checkbox = self._qt.QCheckBox(self._translator.text("preview.export_full_diff"))
        checkbox.setChecked(False)
        layout.addWidget(checkbox)
        actions = self._qt.QHBoxLayout()
        actions.addStretch(1)
        cancel = self._qt.QPushButton(self._translator.text("common.cancel"))
        confirm = self._qt.QPushButton(self._translator.text("preview.export"))
        actions.addWidget(cancel)
        actions.addWidget(confirm)
        layout.addLayout(actions)
        cancel.clicked.connect(dialog.reject)
        confirm.clicked.connect(dialog.accept)
        if exec_dialog(dialog) != 1:
            return
        include_full_diff = checkbox.isChecked()
        try:
            export(self._planned, self._previews, include_full_diff, self._qt, self.dialog)
        except Exception as error:
            self._qt.QMessageBox.warning(
                self.dialog,
                plugin_window_title(
                    self._translator, self._translator.text("preview.export")),
                self._translator.text("preview.export_failed", reason=str(error)),
            )

    def _open_batch_decision(self, initial_scope: str = "filtered") -> None:
        if not self._entries:
            return
        qt = self._qt
        selected_scope = initial_scope
        selected_action = "accept"
        only_undecided = True
        stale = False
        while True:
            current = self._current_entry()
            current_file_id = current[1].file_id if current is not None else None
            before_revision = tuple(
                (file_id, preview.decision_revision)
                for file_id, preview in self._preview_by_file_id.items()
            )
            dialog = qt.QDialog(self.dialog)
            dialog.setWindowTitle(self._translator.text("preview.batch_title"))
            layout = qt.QVBoxLayout(dialog)
            form = qt.QFormLayout()
            scope_combo = qt.QComboBox()
            for label_key, value in (
                ("preview.batch_scope_filtered", "filtered"),
                ("preview.batch_scope_file", "file"),
                ("preview.batch_scope_all", "all"),
            ):
                scope_combo.addItem(self._translator.text(label_key), value)
            file_index = scope_combo.findData("file")
            if current_file_id is None:
                model = scope_combo.model()
                model_item = model.item(file_index) if model is not None else None
                if model_item is not None:
                    model_item.setEnabled(False)
                    model_item.setToolTip(
                        self._translator.text("preview.batch_file_unavailable"))
            scope_combo.setCurrentIndex(scope_combo.findData(selected_scope))
            form.addRow(
                qt.QLabel(self._translator.text("preview.batch_scope_label")), scope_combo)
            action_combo = qt.QComboBox()
            action_combo.addItem(self._translator.text("preview.batch_accept"), "accept")
            action_combo.addItem(self._translator.text("preview.batch_skip"), "skip")
            action_combo.setCurrentIndex(action_combo.findData(selected_action))
            form.addRow(
                qt.QLabel(self._translator.text("preview.batch_action_label")), action_combo)
            layout.addLayout(form)
            only_check = qt.QCheckBox(self._translator.text("preview.batch_only_undecided"))
            only_check.setChecked(only_undecided)
            layout.addWidget(only_check)
            summary = qt.QLabel()
            summary.setWordWrap(True)
            layout.addWidget(summary)
            if stale:
                stale_label = qt.QLabel(self._translator.text("preview.batch_stale"))
                stale_label.setWordWrap(True)
                layout.addWidget(stale_label)
            buttons = qt.QHBoxLayout()
            buttons.addStretch(1)
            cancel = qt.QPushButton(self._translator.text("common.cancel"))
            confirm = qt.QPushButton()
            buttons.addWidget(cancel)
            buttons.addWidget(confirm)
            layout.addLayout(buttons)
            cancel.clicked.connect(dialog.reject)

            def build_plan(
                scope_combo=scope_combo, action_combo=action_combo,
                only_check=only_check, current_file_id=current_file_id,
            ):
                visible = self._visible_entries_cache
                return plan_batch_decision(
                    self._entries, self._group_entries_by_id, self._group_file_ids,
                    scope=scope_combo.currentData() or "filtered",
                    visible_change_ids=(id(change) for _preview, change in visible),
                    file_id=current_file_id,
                    entries_by_file=getattr(self, "_entries_by_file", None),
                    accepted=(action_combo.currentData() != "skip"),
                    undecided_only=only_check.isChecked(),
                )

            batch_plan = None

            def refresh_batch_summary(
                *_args, action_combo=action_combo, only_check=only_check,
                summary=summary, confirm=confirm,
            ):
                nonlocal batch_plan
                batch_plan = build_plan()
                batch = batch_plan
                summary_parts = []
                if batch.change_count:
                    action = self._translator.text(
                        "preview.batch_action_accept"
                        if action_combo.currentData() != "skip"
                        else "preview.batch_action_skip")
                    if batch.change_count == 1:
                        summary_key = "preview.batch_summary_main_one"
                    elif batch.file_count == 1:
                        summary_key = "preview.batch_summary_main_many_one_file"
                    else:
                        summary_key = "preview.batch_summary_main_many_files"
                    summary_parts.append(self._translator.text(
                        summary_key,
                        action=action,
                        changes=batch.change_count,
                        files=batch.file_count,
                    ))
                else:
                    summary_parts.append(self._translator.text("preview.batch_summary_main_none"))
                for key, count in (
                    ("preview.batch_summary_part_groups", batch.group_count),
                    ("preview.batch_summary_part_hidden", batch.hidden_count),
                    ("preview.batch_summary_part_overwrite", batch.overwrite_count),
                    ("preview.batch_summary_part_mixed", batch.excluded_mixed_groups),
                    ("preview.batch_summary_part_language", batch.excluded_language_groups),
                    ("preview.batch_summary_part_other", batch.excluded_other_groups),
                ):
                    if count:
                        summary_parts.append(self._translator.text(key, count=count))
                separator = "" if self._translator.language.startswith("zh") else " "
                summary.setText(separator.join(summary_parts))
                confirm_key = (
                    "preview.batch_confirm_none" if batch.change_count == 0 else
                    "preview.batch_confirm_overwrite"
                    if batch.overwrite_count and not only_check.isChecked()
                    else "preview.batch_confirm"
                )
                confirm.setText(self._translator.text(
                    confirm_key,
                    count=batch.change_count, overwrite=batch.overwrite_count,
                ))
                confirm.setEnabled(batch.change_count > 0)

            scope_combo.currentIndexChanged.connect(refresh_batch_summary)
            action_combo.currentIndexChanged.connect(refresh_batch_summary)
            only_check.toggled.connect(refresh_batch_summary)
            refresh_batch_summary()
            confirm.clicked.connect(dialog.accept)
            if exec_dialog(dialog) != 1:
                return
            selected_scope = str(scope_combo.currentData() or "filtered")
            selected_action = str(action_combo.currentData() or "accept")
            only_undecided = only_check.isChecked()
            current_revision = tuple(
                (file_id, preview.decision_revision)
                for file_id, preview in self._preview_by_file_id.items()
            )
            if current_revision != before_revision:
                stale = True
                continue
            batch = batch_plan if batch_plan is not None else build_plan()
            if batch.change_count <= 0:
                return
            accepted = selected_action != "skip"
            target = (PreviewDecision.ACCEPT_THIS if accepted
                      else PreviewDecision.REJECT_THIS)
            before_decisions = self._capture_compact_decisions(batch.entries)
            for file_id, change_ids, _states in before_decisions:
                self._preview_by_file_id[file_id].restore_decisions(change_ids, target)
            self._record_scoped_bulk_decision_action(
                before_decisions, target, batch.change_count)
            self._record_decision_changes_bulk(before_decisions, target)
            feedback = self._translator.text(
                "preview.batch_applied_main", changes=batch.change_count)
            if batch.group_count > 0:
                separator = "" if self._translator.language.startswith("zh") else " "
                feedback += separator + self._translator.text(
                    "preview.batch_applied_groups", groups=batch.group_count)
            self._last_group_feedback = feedback
            self._refresh_after_decision(batch.entries)
            return

    @staticmethod
    def _populate_filter(
        combo: Any, label: str, values: Sequence[tuple[str, str]], translator: Translator,
    ) -> None:
        combo.addItem(
            f"{label}{translator.text('common.label_separator')}"
            f"{translator.text('preview.filter_all')}", None)
        for display, value in values:
            combo.addItem(str(display), str(value))

    def _source_filter_label(self, source: str) -> str:
        if source.startswith("UserRule:"):
            return self._translator.text(
                "preview.source.user_rule", source=source.removeprefix("UserRule:"))
        if source.startswith("OpenCC:"):
            return self._translator.text(
                "preview.source.opencc", source=source.removeprefix("OpenCC:"))
        return self._translator.text("preview.source.named", source=source)

    def _schedule_filter_refresh(self, *_args) -> None:
        timer = getattr(self, "_search_refresh_timer", None)
        if timer is None:
            self._refresh()
        else:
            timer.start()

    def _clear_filters(self) -> None:
        for name in (
            "file_filter", "category_filter", "risk_filter", "source_filter", "status_filter",
        ):
            combo = getattr(self, name, None)
            if combo is None:
                continue
            was_blocked = combo.blockSignals(True) if callable(
                getattr(combo, "blockSignals", None)) else False
            combo.setCurrentIndex(0)
            if callable(getattr(combo, "blockSignals", None)):
                combo.blockSignals(was_blocked)
        search = self.search_input
        search_blocked = search.blockSignals(True) if callable(
            getattr(search, "blockSignals", None)) else False
        search.setText("")
        if callable(getattr(search, "blockSignals", None)):
            search.blockSignals(search_blocked)
        timer = getattr(self, "_search_refresh_timer", None)
        if timer is not None:
            timer.stop()
        self._refresh()

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
            rule_source=data("source_filter"),
        )

    def _visible_entries(self) -> tuple[tuple[PreviewSession, TokenChange], ...]:
        current = self._current_filter()
        status_combo = getattr(self, "status_filter", None)
        status = None
        if status_combo is not None and callable(getattr(status_combo, "currentData", None)):
            status = status_combo.currentData()
        status = str(status) if status else None
        search_input = getattr(self, "search_input", None)
        query = (search_input.text() if search_input is not None
                 and callable(getattr(search_input, "text", None)) else "")
        query = str(query).strip().casefold()
        if not any((current.file_id, current.category, current.risk,
                    current.rule_source, status, query)):
            return self._entries
        visible = []
        for preview, change in self._entries:
            if not self._matches_non_status_filters(change, current=current, query=query):
                continue
            if status and self._decision_bucket(
                    preview.decision(change.change_id)) != status:
                continue
            visible.append((preview, change))
        return tuple(visible)

    def _matches_non_status_filters(self, change, *, current=None, query=None):
        current = self._current_filter() if current is None else current
        if not current.matches(change):
            return False
        if query is None:
            search_input = getattr(self, "search_input", None)
            query = (search_input.text() if search_input is not None
                     and callable(getattr(search_input, "text", None)) else "")
            query = str(query).strip().casefold()
        if not query:
            return True
        href = self._href_by_id.get(change.file_id, change.file_id)
        searchable = "\n".join((
            unescape(change.source), unescape(change.target), change.rule_source, href,
        )).casefold()
        return query in searchable

    def _status_filter_value(self) -> str | None:
        combo = getattr(self, "status_filter", None)
        if combo is None or not callable(getattr(combo, "currentData", None)):
            return None
        value = combo.currentData()
        return str(value) if value else None

    @staticmethod
    def _decision_bucket(decision) -> str:
        if decision is None:
            return "undecided"
        return "accepted" if decision.value.startswith("accept") else "rejected"

    def _recompute_counts(self) -> None:
        entries = getattr(self, "_entries", ())
        all_undecided = all(
            preview.decision_revision == 0 for preview in getattr(self, "_previews", ()))
        initial_counts = getattr(self, "_initial_file_change_counts", None)
        if (all_undecided and initial_counts is not None
                and getattr(self, "_one_file_per_preview", False)):
            self._totals = {
                "total": sum(initial_counts.values()),
                "accepted": 0,
                "rejected": 0,
                "undecided": sum(initial_counts.values()),
            }
            self._file_filter_counts = {
                file_id: (count, count)
                for file_id, count in initial_counts.items()
            }
            self._accepted_count_by_file = {}
            return
        self._totals = {
            "total": len(entries), "accepted": 0, "rejected": 0, "undecided": 0,
        }
        self._file_filter_counts = {}
        self._accepted_count_by_file = {}
        for preview, change in entries:
            bucket = (
                "undecided" if all_undecided
                else self._decision_bucket(preview.decision(change.change_id))
            )
            self._totals[bucket] += 1
            total, pending = self._file_filter_counts.get(change.file_id, (0, 0))
            self._file_filter_counts[change.file_id] = (
                total + 1, pending + (bucket == "undecided"),
            )
            if bucket == "accepted":
                self._accepted_count_by_file[change.file_id] = (
                    self._accepted_count_by_file.get(change.file_id, 0) + 1
                )

    def _record_decision_change(self, file_id, before, after) -> None:
        if not hasattr(self, "_totals"):
            self._recompute_counts()
        old_bucket = self._decision_bucket(before)
        new_bucket = self._decision_bucket(after)
        if old_bucket == new_bucket:
            return
        self._totals[old_bucket] -= 1
        self._totals[new_bucket] += 1

        total, pending = self._file_filter_counts.get(file_id, (0, 0))
        if old_bucket == "undecided":
            pending -= 1
        if new_bucket == "undecided":
            pending += 1
        self._file_filter_counts[file_id] = (total, pending)

        accepted = self._accepted_count_by_file.get(file_id, 0)
        if old_bucket == "accepted":
            accepted -= 1
        if new_bucket == "accepted":
            accepted += 1
        if accepted:
            self._accepted_count_by_file[file_id] = accepted
        else:
            self._accepted_count_by_file.pop(file_id, None)

    def _record_decision_changes_bulk(self, before_decisions, after) -> None:
        if not hasattr(self, "_totals"):
            self._recompute_counts()
        target_bucket = self._decision_bucket(after)
        for file_id, change_ids, states in before_decisions:
            count = len(change_ids)
            old_undecided = states.count(0)
            old_accepted = sum(states.count(code) for code in _ACCEPTED_DECISION_CODES)
            old_rejected = sum(states.count(code) for code in _REJECTED_DECISION_CODES)
            new_undecided = count if target_bucket == "undecided" else 0
            new_accepted = count if target_bucket == "accepted" else 0
            new_rejected = count if target_bucket == "rejected" else 0
            self._totals["undecided"] += new_undecided - old_undecided
            self._totals["accepted"] += new_accepted - old_accepted
            self._totals["rejected"] += new_rejected - old_rejected

            total, pending = self._file_filter_counts.get(file_id, (0, 0))
            pending += new_undecided - old_undecided
            self._file_filter_counts[file_id] = (total, pending)

            accepted = self._accepted_count_by_file.get(file_id, 0)
            accepted += new_accepted - old_accepted
            if accepted:
                self._accepted_count_by_file[file_id] = accepted
            else:
                self._accepted_count_by_file.pop(file_id, None)

    def _record_decision_changes(self, before) -> None:
        for file_id, change_id, previous in before:
            preview = self._preview_by_file_id[file_id]
            self._record_decision_change(
                file_id, previous, preview.decision(change_id))

    def _refresh_after_decision(self, affected) -> None:
        """Refresh changed rows without rescanning a large status-filtered preview."""

        self._selection_advanced_scan_start = None
        status = self._status_filter_value()
        if status is None:
            self._refresh(refresh_statuses=True)
            return

        visible = self._visible_entries_cache
        affected = tuple(affected)
        current_row = self._current_row()

        removed_rows = []
        refreshed_rows = []
        current_filter = self._current_filter()
        search_input = getattr(self, "search_input", None)
        query = (search_input.text() if search_input is not None
                 and callable(getattr(search_input, "text", None)) else "")
        query = str(query).strip().casefold()

        for preview, change in affected:
            identity = (change.file_id, change.change_id)
            position = self._entry_position.get(identity)
            row = None
            if position is not None:
                candidate = bisect_left(self._visible_positions, position)
                if (candidate < len(self._visible_positions)
                        and self._visible_positions[candidate] == position):
                    row = candidate
            non_status_match = self._matches_non_status_filters(
                change, current=current_filter, query=query)
            now_visible = (
                non_status_match
                and self._decision_bucket(preview.decision(change.change_id)) == status
            )
            if row is None:
                if now_visible:
                    self._refresh(refresh_statuses=True)
                    return
                continue
            if now_visible:
                refreshed_rows.append(row)
            else:
                removed_rows.append(row)

        removed_rows = sorted(set(removed_rows))
        ranges = []
        for row in removed_rows:
            if ranges and row == ranges[-1][1] + 1:
                ranges[-1] = (ranges[-1][0], row)
            else:
                ranges.append((row, row))

        if ranges:
            next_entries = visible
            next_positions = self._visible_positions
            model = getattr(self, "table_model", None)
            for first, last in reversed(ranges):
                model_entries = getattr(getattr(model, "rows", None), "entries", None)
                if model_entries is not None and (
                    first < 0 or last < first or last >= len(model_entries)
                ):
                    self._refresh(refresh_statuses=True)
                    return
                next_entries = next_entries[:first] + next_entries[last + 1:]
                if model is not None:
                    prior_model_entries = getattr(getattr(model, "rows", None), "entries", None)
                    updated_model_entries = model.remove_rows(((first, last),))
                    if updated_model_entries is prior_model_entries:
                        self._refresh(refresh_statuses=True)
                        return
                next_positions = next_positions[:first] + next_positions[last + 1:]
            self._visible_entries_cache = next_entries
            self._visible_positions = next_positions
            if current_row in removed_rows:
                self._selection_advanced_scan_start = current_row - 1
            current_row -= sum(row < current_row for row in removed_rows)
            if next_entries:
                current_row = min(max(current_row, 0), len(next_entries) - 1)
                self._set_current_row(current_row)
                if model is not None and refreshed_rows:
                    shifted_rows = tuple(
                        row - sum(removed < row for removed in removed_rows)
                        for row in refreshed_rows
                    )
                    model.refresh(rows=shifted_rows)
                self._show_current(current_row)
            else:
                self._set_current_row(-1)
                empty_key = "preview.no_filter_matches" if self._entries else "preview.no_changes"
                self.detail.setPlainText(self._translator.text(empty_key))
        else:
            model = getattr(self, "table_model", None)
            if model is not None and refreshed_rows:
                model.refresh(rows=refreshed_rows)
            if 0 <= current_row < len(visible):
                self._show_current(current_row)

        count_label = getattr(self, "filter_count_label", None)
        if count_label is not None:
            count_label.setText(self._translator.text(
                "preview.visible_count", visible=len(self._visible_entries_cache),
                total=len(self._entries)))
        self._refresh_file_filter_counts()
        self._update_summary()

    @staticmethod
    def _unique_entries(entries):
        unique = []
        seen = set()
        for entry in entries:
            change = entry[1]
            identity = (change.file_id, change.change_id)
            if identity not in seen:
                seen.add(identity)
                unique.append(entry)
        return tuple(unique)

    def _capture_decisions(self, entries, *, deduplicate=True):
        if deduplicate:
            entries = self._unique_entries(entries)
        return tuple(
            (change.file_id, change.change_id, preview.decision(change.change_id))
            for preview, change in entries
        )

    def _record_decision_action(self, before):
        changes = []
        preview_by_file_id = self._preview_by_file_id
        for file_id, change_id, previous in before:
            current = preview_by_file_id[file_id].decision(change_id)
            if previous != current:
                changes.append(_DecisionHistoryChange(
                    file_id=file_id,
                    change_id=change_id,
                    before=previous,
                    after=current,
                ))
        changes = tuple(changes)
        if not changes:
            return
        self._history_sequence += 1
        operation = _DecisionHistoryOperation(self._history_sequence, changes)
        self._push_decision_history(operation)

    @staticmethod
    def _capture_compact_decisions(entries):
        grouped = {}
        for preview, change in entries:
            record = grouped.setdefault(change.file_id, [[], bytearray()])
            record[0].append(change.change_id)
            decision = preview.decision(change.change_id)
            record[1].append(0 if decision is None else _DECISION_TO_CODE[decision])
        return tuple((file_id, tuple(change_ids), bytes(states))
                     for file_id, (change_ids, states) in grouped.items())

    def _record_scoped_bulk_decision_action(self, before_decisions, after, change_count):
        if change_count <= 0:
            return
        self._history_sequence += 1
        operation = _ScopedBulkDecisionHistoryOperation(
            self._history_sequence, tuple(before_decisions), after, change_count,
        )
        self._push_decision_history(operation)

    def _push_decision_history(self, operation):
        if self._redo_stack:
            self._history_record_count -= sum(
                len(item.changes) for item in self._redo_stack)
            self._redo_stack.clear()
        self._undo_stack.append(operation)
        self._history_record_count += len(operation.changes)
        self._prune_decision_history()
        if hasattr(self, "undo_button"):
            self._update_history_controls()

    def _prune_decision_history(self):
        self._history_feedback = ""
        while True:
            operations = [
                (operation.sequence, stack, operation)
                for stack in (self._undo_stack, self._redo_stack)
                for operation in stack
            ]
            if (
                len(operations) <= _MAX_DECISION_HISTORY_OPERATIONS
                and self._history_record_count <= _MAX_DECISION_HISTORY_CHANGES
            ):
                return
            _sequence, stack, oldest = min(operations, key=lambda item: item[0])
            if len(oldest.changes) > _MAX_DECISION_HISTORY_CHANGES:
                self._undo_stack.clear()
                self._redo_stack.clear()
                self._undo_stack.append(oldest)
                self._history_record_count = len(oldest.changes)
                self._history_feedback = self._translator.text(
                    "preview.history_large_operation")
                return
            stack.remove(oldest)
            self._history_record_count -= len(oldest.changes)

    def _clear_decision_history(self):
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._history_record_count = 0
        self._history_feedback = ""
        if hasattr(self, "undo_button"):
            self._update_history_controls()

    def _update_history_controls(self):
        undo_button = getattr(self, "undo_button", None)
        redo_button = getattr(self, "redo_button", None)
        reset_button = getattr(self, "reset_current_button", None)
        if undo_button is None or redo_button is None or reset_button is None:
            return
        undo_button.setEnabled(bool(getattr(self, "_undo_stack", ())))
        redo_button.setEnabled(bool(getattr(self, "_redo_stack", ())))
        entry = self._current_entry()
        can_reset = bool(
            entry is not None and entry[0].decision(entry[1].change_id) is not None
        )
        reset_button.setEnabled(can_reset)

    def _apply_history_side(self, operation, side):
        if isinstance(operation, _ScopedBulkDecisionHistoryOperation):
            for file_id, change_ids, states in operation.before_decisions:
                preview = self._preview_by_file_id[file_id]
                if side == "before":
                    for change_id, state in zip(change_ids, states):
                        preview.restore_decision(
                            change_id, None if state == 0 else _DECISION_VALUES[state - 1])
                else:
                    for change_id in change_ids:
                        preview.restore_decision(change_id, operation.after)
            self._recompute_counts()
            return
        for change in operation.changes:
            preview = self._preview_by_file_id[change.file_id]
            before = preview.decision(change.change_id)
            after = getattr(change, side)
            preview.restore_decision(change.change_id, after)
            self._record_decision_change(change.file_id, before, after)

    def _undo_preview_action(self):
        if not self._undo_stack:
            return
        operation = self._undo_stack.pop()
        self._apply_history_side(operation, "before")
        self._redo_stack.append(operation)
        self._refresh(refresh_statuses=True)

    def _redo_preview_action(self):
        if not self._redo_stack:
            return
        operation = self._redo_stack.pop()
        self._apply_history_side(operation, "after")
        self._undo_stack.append(operation)
        self._refresh(refresh_statuses=True)

    def _reset_current_to_undecided(self):
        entry = self._current_entry()
        if entry is None:
            return
        _preview, change = entry
        entries = (
            getattr(self, "_group_entries_by_id", {}).get(change.group_id, (entry,))
            if change.group_id else (entry,)
        )
        before = self._capture_decisions(entries)
        for preview, item in entries:
            if preview.decision(item.change_id) is not None:
                preview.restore_decision(item.change_id, None)
        self._record_decision_changes(before)
        self._record_decision_action(before)
        self._refresh_after_decision(entries)

    def _current_row(self) -> int:
        table = getattr(self, "table_view", None)
        if table is None:
            return -1
        index = table.currentIndex()
        return index.row() if index.isValid() else -1

    def _selected_change_identity(self) -> tuple[str, str] | None:
        row = self._current_row()
        entries = self._visible_entries_cache
        if 0 <= row < len(entries):
            change = entries[row][1]
            return change.file_id, change.change_id
        return None

    def _navigate_to_related_change(self, identity: tuple[str, str]) -> None:
        """Reveal a real related preview row without changing its decision."""

        self._clear_filters()
        file_id, _change_id = identity
        for index in range(self.file_filter.count()):
            if self.file_filter.itemData(index) == file_id:
                self.file_filter.setCurrentIndex(index)
                break
        self._refresh()
        visible_entries = self._visible_entries_cache
        row = next(
            (index for index, (_preview, change) in enumerate(visible_entries)
             if (change.file_id, change.change_id) == identity),
            None,
        )
        if row is not None:
            self._set_current_row(row)
            self.detail_tabs.setCurrentIndex(0)

    def _set_current_row(self, row: int) -> None:
        table = getattr(self, "table_view", None)
        if table is None:
            return
        if row < 0:
            table.clearSelection()
            table.setCurrentIndex(self.table_model.index(-1, 0))
            return
        table.setCurrentIndex(self.table_model.index(row, 0))
        table.selectRow(row)

    def _diagnostics_for_file(self, file_id: str | None = None) -> tuple[str, ...]:
        counts = Counter()
        for planned in getattr(self, "_planned", ()):
            plan = getattr(planned, "plan", None)
            if plan is None or (file_id and getattr(plan, "file_id", "") != file_id):
                continue
            for diagnostic in getattr(plan, "diagnostics", ()):
                code = str(getattr(diagnostic, "code", ""))
                if code:
                    counts[code] += 1
        return tuple(
            diagnostic_summary(self._translator, code, count)
            for code, count in sorted(counts.items())
        )

    def _skipped_source_details(self) -> tuple[str, ...]:
        rows = []
        for planned in getattr(self, "_planned", ()):
            source = getattr(planned, "source", None)
            plan = getattr(planned, "plan", None)
            if plan is None:
                continue
            href = getattr(source, "href", getattr(plan, "file_id", ""))
            for diagnostic in getattr(plan, "diagnostics", ()):
                line = getattr(diagnostic, "line", None)
                column = getattr(diagnostic, "column", None)
                if (getattr(diagnostic, "code", "") != "SOURCE_INVALID_XHTML"
                        or line is None or column is None):
                    continue
                location = self._translator.text(
                    "preview.invalid_source_location",
                    line=line,
                    column=column,
                )
                rows.append(
                    f"{href}{self._translator.text('common.label_separator')}{location}"
                )
        return tuple(rows)

    def _refresh(self, *_args, recalculate_counts=False, refresh_statuses=False) -> None:
        if recalculate_counts:
            self._recompute_counts()
        self._selection_advanced_scan_start = None
        cached_entries = self._visible_entries_cache
        status_filter_active = self._status_filter_value() is not None
        if refresh_statuses and not status_filter_active:
            # Decisions change row status, not which rows match the filters.
            # Keep the tuple/model identity and avoid rescanning large books.
            visible_entries = cached_entries
            row = self._current_row()
            if row < 0 and visible_entries:
                row = 0
        else:
            selected_identity = self._selected_change_identity()
            previous_row = self._current_row()
            visible_entries = self._visible_entries()
            selected_row = next(
                (index for index, (_preview, change) in enumerate(visible_entries)
                 if (change.file_id, change.change_id) == selected_identity),
                None,
            )
            if selected_row is not None:
                row = selected_row
            elif visible_entries and status_filter_active:
                row = min(max(previous_row, 0), len(visible_entries) - 1)
                if selected_identity is not None:
                    self._selection_advanced_scan_start = previous_row - 1
            else:
                row = 0 if visible_entries else -1
        if visible_entries is not cached_entries:
            self._visible_positions = [
                self._entry_position[(change.file_id, change.change_id)]
                for _preview, change in visible_entries
            ]
        self._visible_entries_cache = visible_entries
        if getattr(self, "table_model", None) is not None:
            prior_entries = self.table_model.rows.entries
            self.table_model.set_entries(visible_entries)
            if refresh_statuses and prior_entries is visible_entries:
                self.table_model.refresh()
            self._set_current_row(row)
        if visible_entries:
            self._show_current(row)
        else:
            empty_key = "preview.no_filter_matches" if self._entries else "preview.no_changes"
            self.detail.setPlainText(self._translator.text(empty_key))
        count_label = getattr(self, "filter_count_label", None)
        if count_label is not None:
            count_label.setText(self._translator.text(
                "preview.visible_count", visible=len(visible_entries), total=len(self._entries)))
        more_filters = getattr(self, "more_filters_button", None)
        if more_filters is not None:
            active = sum(getattr(self, name).currentData() is not None for name in (
                "file_filter", "category_filter", "risk_filter", "source_filter"))
            more_filters.setText(self._translator.text("preview.more_filters", count=active))
        self._update_summary()

    def _update_summary(self) -> None:
        if not hasattr(self, "_totals"):
            self._recompute_counts()
        totals = self._totals
        summary = self._translator.text("preview.summary", files=len(self._previews), **totals)
        diagnostics = self._diagnostics_for_file()
        if diagnostics:
            summary += "\n" + self._translator.text("preview.diagnostics", details="; ".join(diagnostics))
        skipped_sources = self._skipped_source_details()
        if skipped_sources:
            visible_sources = skipped_sources
            if len(skipped_sources) > 3:
                visible_sources = (
                    *skipped_sources[:3],
                    self._translator.text(
                        "preview.skipped_sources_more", count=len(skipped_sources) - 3),
                )
                self.summary.setToolTip(self._translator.text(
                    "preview.skipped_sources", files="\n".join(skipped_sources)))
            else:
                self.summary.setToolTip("")
            summary += "\n" + self._translator.text(
                "preview.skipped_sources", files="\n".join(visible_sources))
        else:
            self.summary.setToolTip("")
        group_feedback = getattr(self, "_last_group_feedback", "")
        if group_feedback:
            summary += "\n" + group_feedback
        history_feedback = getattr(self, "_history_feedback", "")
        if history_feedback:
            summary += "\n" + history_feedback
        self.summary.setText(summary)
        self._refresh_file_filter_counts()
        has_current = bool(self._visible_entries_cache)
        for name in (
            "accept_this_button",
            "reject_this_button",
            "next_undecided_button",
        ):
            button = getattr(self, name, None)
            if button is not None:
                button.setEnabled(has_current)
                action = getattr(self, "_more_action_by_button", {}).get(button)
                if action is not None:
                    action.setEnabled(has_current)
        # Batch decisions remain available while the preview contains changes.
        # Applying stays blocked until every change has a decision.
        has_entries = bool(self._entries)
        batch_button = getattr(self, "batch_button", None)
        if batch_button is not None:
            batch_button.setEnabled(has_entries)
            action = getattr(self, "_more_action_by_button", {}).get(batch_button)
            if action is not None:
                action.setEnabled(has_entries)
        self._update_history_controls()
        accepted_files = self._accepted_count_by_file
        complete = totals["undecided"] == 0
        accepted_count = totals["accepted"]
        if not complete:
            self.apply_button.setText(self._translator.text("preview.apply"))
            status_key = "preview.apply_status_pending"
            status_values = {"count": totals["undecided"]}
        elif accepted_count:
            apply_key = (
                "preview.apply_decisions_one"
                if accepted_count == 1
                else "preview.apply_decisions_many"
            )
            file_count_key = (
                "preview.file_count_one"
                if len(accepted_files) == 1
                else "preview.file_count_many"
            )
            self.apply_button.setText(self._translator.text(
                apply_key,
                changes=accepted_count,
                files=self._translator.text(
                    file_count_key, count=len(accepted_files)),
            ))
            status_key = "preview.apply_status_ready"
            status_values = {}
        else:
            self.apply_button.setText(self._translator.text("preview.apply_no_changes"))
            status_key = "preview.apply_status_none"
            status_values = {}
        status_label = getattr(self, "apply_status_label", None)
        if status_label is not None:
            status_label.setText(
                self._translator.text(status_key, **status_values)
                + "\n" + self._translator.text("preview.shortcut_hint")
            )
        self.apply_button.setEnabled(complete)
        set_tooltip = getattr(self.apply_button, "setToolTip", None)
        if callable(set_tooltip):
            set_tooltip("" if complete else self._translator.text("preview.incomplete"))
        resolve_remaining = getattr(self, "resolve_remaining_button", None)
        if resolve_remaining is not None:
            remaining = totals["undecided"]
            resolve_remaining.setText(self._translator.text(
                "preview.resolve_remaining", count=remaining))
            resolve_remaining.setVisible(remaining > 0)
            resolve_remaining.setEnabled(remaining > 0)

    def _refresh_file_filter_counts(self) -> None:
        combo = getattr(self, "file_filter", None)
        if combo is None or not callable(getattr(combo, "setItemText", None)):
            return
        if not hasattr(self, "_file_filter_counts"):
            self._recompute_counts()
        file_counts = self._file_filter_counts
        selected = combo.currentData()
        previous_blocked = combo.blockSignals(True) if callable(
            getattr(combo, "blockSignals", None)) else False
        try:
            href_by_id = getattr(self, "_href_by_id", {})
            kind_by_id = getattr(self, "_kind_by_id", {})
            for index in range(1, combo.count()):
                file_id = combo.itemData(index)
                if file_id not in file_counts:
                    continue
                total, pending = file_counts[file_id]
                href = (
                    self._translator.text("preview.file.metadata")
                    if kind_by_id.get(file_id) == "metadata"
                    else href_by_id.get(file_id, file_id)
                )
                combo.setItemText(index, self._translator.text(
                    "preview.filter_file_option", href=href,
                    changes=total, undecided=pending))
            if selected is not None:
                for index in range(combo.count()):
                    if combo.itemData(index) == selected:
                        combo.setCurrentIndex(index)
                        break
        finally:
            if callable(getattr(combo, "blockSignals", None)):
                combo.blockSignals(previous_blocked)

    def _show_current(self, row: int) -> None:
        visible_entries = self._visible_entries_cache
        if row < 0 or row >= len(visible_entries):
            self.detail.clear()
            self.source_detail.clear()
            self.target_detail.clear()
            if hasattr(self, "undo_button"):
                self._update_history_controls()
            return
        preview, change = visible_entries[row]
        diagnostics = self._diagnostics_for_file(change.file_id)
        diagnostic_text = (
            "\n" + self._translator.text("preview.diagnostic_detail", details="; ".join(diagnostics))
            if diagnostics
            else ""
        )
        show_source = getattr(self, "show_source_context", None)
        if show_source is not None and show_source.isChecked():
            context_before, context_after = _source_context(change, self._source_by_id)
        else:
            context_before, context_after = _text_context(change, self._targets_by_id)
        context_before = _single_line(context_before)
        context_after = _single_line(context_after)
        source_line = f"{context_before}【{_single_line(unescape(change.source))}】{context_after}"
        target_line = f"{context_before}【{_single_line(unescape(change.target))}】{context_after}"
        group_text = ""
        if change.group_id:
            count, files = getattr(self, "_group_stats", {}).get(change.group_id, (1, 1))
            explanation_key = _group_explanation_key(change.group_id)
            group_text = "\n" + self._translator.text(
                explanation_key, count=count, files=files)
        separator = self._translator.text("common.label_separator")
        decision = preview.decision(change.change_id)
        decision_state = (
            "accepted" if decision is not None and decision.value.startswith("accept")
            else "skipped" if decision is not None and decision.value.startswith("reject")
            else "pending"
        )
        self.detail.setPlainText("\n".join((
            f"{self._translator.text('preview.rule')}{separator}"
            f"{self._source_filter_label(change.rule_source)}",
            f"{self._translator.text('preview.category')}{separator}"
            f"{self._translator.text(f'preview.category_value.{change.category}')}    "
            f"{self._translator.text('preview.risk')}{separator}"
            f"{self._translator.text(f'preview.risk_value.{change.risk.lower()}')}",
            f"{self._translator.text('preview.status.' + decision_state)}"
            f"{group_text}{diagnostic_text}",
        )))
        self.source_detail.setPlainText(source_line)
        self.target_detail.setPlainText(target_line)
        if hasattr(self, "undo_button"):
            self._update_history_controls()

    def _current_entry(self):
        row = self._current_row()
        visible_entries = self._visible_entries_cache
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
            affected = getattr(self, "_group_entries_by_id", {}).get(change.group_id, (entry,))
            before = self._capture_decisions(affected)
            count = self._decide_group(change.group_id, accepted)
            feedback_key = _group_feedback_key(change.group_id, accepted)
            self._last_group_feedback = self._translator.text(
                feedback_key, count=count)
            self._record_decision_changes(before)
            self._record_decision_action(before)
            self._refresh_after_decision(affected)
        else:
            self._last_group_feedback = ""
            row = self._current_row()
            before = self._capture_decisions((entry,))
            old_decision = preview.decision(change.change_id)
            (preview.accept_this if accepted else preview.reject_this)(change.change_id)
            after = preview.decision(change.change_id)
            self._record_decision_change(change.file_id, old_decision, after)
            self._record_decision_action(before)
            if self._status_filter_value() is not None:
                self._refresh_after_decision((entry,))
            else:
                self._refresh_current(rows=(row,))
        scan_start = self._selection_advanced_scan_start
        self._selection_advanced_scan_start = None
        self._select_next_undecided(change.change_id, start_row=scan_start)

    def _select_next_undecided(
        self, current_change_id=None, *, direction: int = 1, start_row=None,
    ) -> None:
        entries = self._visible_entries_cache
        if not entries:
            return
        current_row = self._current_row() if start_row is None else start_row
        if current_row < 0:
            current_row = -1 if direction > 0 else 0
        for offset in range(1, len(entries) + 1):
            row = (current_row + direction * offset) % len(entries)
            preview, change = entries[row]
            if current_change_id and change.change_id == current_change_id:
                continue
            if preview.decision(change.change_id) is None:
                self._set_current_row(row)
                self._show_current(row)
                return

    def _next_undecided(self) -> None:
        self._select_next_undecided(direction=1)

    def _previous_undecided(self) -> None:
        self._select_next_undecided(direction=-1)

    def _decide_group(self, group_id, accepted):
        count = 0
        entries_by_group = getattr(self, "_group_entries_by_id", None)
        entries = (
            entries_by_group.get(group_id, ())
            if entries_by_group is not None
            else ((preview, change) for preview, change in self._entries
                  if change.group_id == group_id)
        )
        for preview, change in entries:
            (preview.accept_this if accepted else preview.reject_this)(change.change_id)
            count += 1
        return count

    def _refresh_current(self, *, rows=()) -> None:
        row = self._current_row()
        visible_entries = self._visible_entries_cache
        if row < 0 or row >= len(visible_entries):
            self._update_summary()
            return
        if rows and getattr(self, "table_model", None) is not None:
            self.table_model.refresh(rows=rows)
        self._show_current(row)
        self._update_summary()

    def _back_to_settings(self) -> None:
        if self.applied:
            return
        if not self._confirm_discard_decisions():
            return
        self.back_to_settings = True
        self._allow_reject = True
        self.dialog.reject()

    def _guard_reject(self) -> bool:
        if self._allow_reject:
            self._allow_reject = False
            self._clear_decision_history()
            return True
        confirmed = self._confirm_discard_decisions()
        if confirmed:
            self._clear_decision_history()
        return confirmed

    def _confirm_discard_decisions(self) -> bool:
        decided = sum(
            summary["accepted"] + summary["rejected"]
            for summary in (preview.summary() for preview in self._previews)
        )
        if not decided:
            return True
        message_box = getattr(self._qt, "QMessageBox", None)
        if not callable(message_box):
            return False
        box = message_box(self.dialog)
        box.setWindowTitle(plugin_window_title(
            self._translator, self._translator.text("preview.discard_title")))
        box.setText(self._translator.text("preview.discard_message", count=decided))
        discard = box.addButton(
            self._translator.text("preview.discard_yes"), message_box.AcceptRole)
        back = box.addButton(
            self._translator.text("preview.discard_no"), message_box.RejectRole)
        box.setDefaultButton(back)
        exec_dialog(box)
        return box.clickedButton() is discard

    def _checkpoint_confirm(self) -> bool:
        if not any(preview.summary()["accepted"] for preview in self._previews):
            return True
        services = self._services
        if services is not None and not services.checkpoint_notice_enabled():
            return True
        message_box = getattr(self._qt, "QMessageBox", None)
        if not callable(message_box):
            return True
        self.checkpoint_notice_shown = True
        box = message_box(self.dialog)
        box.setWindowTitle(plugin_window_title(
            self._translator, self._translator.text("preview.checkpoint_title")))
        box.setText(self._translator.text("preview.checkpoint_confirm"))
        box.setIcon(message_box.Warning)
        accept = box.addButton(
            self._translator.text("preview.checkpoint_confirm_yes"), message_box.AcceptRole)
        cancel = box.addButton(
            self._translator.text("preview.checkpoint_confirm_back"), message_box.RejectRole)
        box.setDefaultButton(cancel)
        hide = self._qt.QCheckBox(self._translator.text("preview.checkpoint_hide"))
        box.setCheckBox(hide)
        exec_dialog(box)
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
        self._clear_decision_history()
        # Disable before accepting the dialog so a queued/re-entrant click
        # cannot submit the same preview twice.
        self.apply_button.setEnabled(False)
        self.dialog.accept()
