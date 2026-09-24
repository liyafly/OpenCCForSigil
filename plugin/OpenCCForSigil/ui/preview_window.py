"""Minimal Preview UI for the first interactive conversion phase."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from html import unescape
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
from ui.qt import ensure_application, enum_value as _enum_value, exec_dialog, load_qt
from ui.i18n import (
    SUPPORTED_LANGUAGES,
    Translator,
    diagnostic_summary,
    settings_error_message,
    show_error_details,
)


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
    checkpoint_notice_shown: bool = False


@dataclass(frozen=True)
class ConfigOutcome:
    action: str
    configuration: object | None = None


class ProgressReporter:
    """A lightweight progress view driven by workflow file boundaries."""

    def __init__(
        self, qt_widgets: Any, total: int, parent: Any = None,
        translator: Translator | None = None,
    ) -> None:
        self._qt = qt_widgets
        self._translator = translator or Translator("en")
        self._cancelled = False
        self._cancelling = False
        self._non_cancellable = False
        self._closed = False
        self._phase = "analyzing"
        self._total = max(int(total), 1)
        self._value = 0
        self.dialog = qt_widgets.QProgressDialog(
            "", self._translator.text("common.cancel"), 0, self._total, parent
        )
        set_minimum_width = getattr(self.dialog, "setMinimumWidth", None)
        if callable(set_minimum_width):
            set_minimum_width(480)
        set_fixed_width = getattr(self.dialog, "setFixedWidth", None)
        if callable(set_fixed_width):
            set_fixed_width(480)
        self.dialog.setWindowTitle(self._translator.text("progress.title"))
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
            self._translator.text(
                "progress.status",
                phase=self._translator.text("progress.phase.analyzing"),
                index=0,
                total=max(int(total), 0),
                file="…",
            )
        )
        self.dialog.show()
        self._process_events()

    def _mark_cancelled(self) -> None:
        if not self._non_cancellable:
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
        if not self._cancelling:
            self.dialog.setLabelText(
                self._translator.text(
                    "progress.status",
                    phase=self._translator.text(f"progress.phase.{self._phase}"),
                    index=self._value,
                    total=total,
                    file=self._elided_filename(href),
                )
            )
        self._process_events()

    def _elided_filename(self, href: str) -> str:
        full_name = str(href)
        label_method = getattr(self.dialog, "label", None)
        label = label_method() if callable(label_method) else None
        if label is not None:
            set_tooltip = getattr(label, "setToolTip", None)
            if callable(set_tooltip):
                set_tooltip(full_name)
            width_method = getattr(label, "width", None)
            width = (width_method() if callable(width_method) else 0) or 440
        else:
            set_tooltip = getattr(self.dialog, "setToolTip", None)
            if callable(set_tooltip):
                set_tooltip(full_name)
            width = 440

        qt_gui = getattr(self._qt, "QtGui", None)
        font_metrics = getattr(qt_gui, "QFontMetrics", None)
        if callable(font_metrics) and label is not None:
            qt = getattr(self._qt, "Qt", None)
            mode = getattr(qt, "ElideMiddle", None)
            if mode is None:
                mode = getattr(getattr(qt, "TextElideMode", None), "ElideMiddle", None)
            if mode is not None:
                return font_metrics(label.font()).elidedText(full_name, mode, width)
        return _elide_middle_by_width(full_name, width)

    def cancelled(self) -> bool:
        self._process_events()
        return self._cancelled

    def disable_cancel(self) -> None:
        """Keep a non-cancellable phase visible until it safely finishes."""

        self._non_cancellable = True
        set_cancel_button = getattr(self.dialog, "setCancelButton", None)
        if callable(set_cancel_button):
            set_cancel_button(None)
        self._cancelled = False
        qt = getattr(self._qt, "Qt", None)
        flag = _enum_value(qt, "WindowCloseButtonHint")
        set_window_flag = getattr(self.dialog, "setWindowFlag", None)
        if flag is not None and callable(set_window_flag):
            set_window_flag(flag, False)
        self._install_non_cancellable_event_filter()
        # Changing a QWidget window flag can hide it on both Qt 5 and Qt 6.
        self.dialog.show()

    def _install_non_cancellable_event_filter(self) -> None:
        qt_core = getattr(self._qt, "QtCore", None)
        qobject = getattr(qt_core, "QObject", None)
        qevent = getattr(qt_core, "QEvent", None)
        if qobject is None or qevent is None:
            return
        event_types = getattr(qevent, "Type", qevent)
        close_type = getattr(qevent, "Close", getattr(event_types, "Close", None))
        key_press_type = getattr(qevent, "KeyPress", getattr(event_types, "KeyPress", None))
        escape_key = _enum_value(getattr(self._qt, "Qt", None), "Key_Escape")
        if close_type is None or key_press_type is None or escape_key is None:
            return

        class _ProgressEventFilter(qobject):
            def eventFilter(_self, _target, event):
                if self._closed:
                    return False
                if event.type() == close_type:
                    return True
                return event.type() == key_press_type and event.key() == escape_key

        self._close_filter = _ProgressEventFilter(self.dialog)
        install_filter = getattr(self.dialog, "installEventFilter", None)
        if callable(install_filter):
            install_filter(self._close_filter)

    def set_cancelling(self) -> None:
        """Keep the progress window visible while the worker reaches a safe stop."""

        self._cancelling = True
        self.dialog.setLabelText(self._translator.text("progress.cancelling"))
        set_cancel_button = getattr(self.dialog, "setCancelButton", None)
        if callable(set_cancel_button):
            set_cancel_button(None)
        self.dialog.show()
        self._process_events()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.dialog.close()

    def _process_events(self) -> None:
        process_events = getattr(self._qt.QApplication, "processEvents", None)
        if callable(process_events):
            process_events()


def _elide_middle_by_width(value: str, width: int) -> str:
    max_characters = max(8, int(width) // 8)
    if len(value) <= max_characters:
        return value
    left_count = (max_characters - 1) // 2
    right_count = max_characters - left_count - 1
    return f"{value[:left_count]}…{value[-right_count:]}"


CONFIG_SELECTION_ORDER = V1_CONFIGS


def _load_ui_qt(translator: Translator):
    try:
        return load_qt()
    except RuntimeError as exc:
        raise UIUnavailableError(translator.text("error.ui_unavailable")) from exc


def choose_conversion_config(
    available_configs: Sequence[str],
    *,
    default_config: str = "s2t",
    jieba_probe=None,
    initial_options=None,
    metadata_available=True,
    nav_available=True,
    services=None,
    ui_preferences=None,
    save_ui_preferences=None,
    translator: Translator | None = None,
) -> ConfigOutcome:
    """Ask for an explicit conversion direction before building a plan.

    This selector exposes pinned upstream standard configs and, when the
    selected payload proves the official native plugin is present, an advanced
    Jieba checkbox. The selected concrete config is frozen into the plan.
    """

    translator = translator or Translator("en")
    qt_widgets = _load_ui_qt(translator)
    available = set(available_configs)
    configs = tuple(config for config in CONFIG_SELECTION_ORDER if config in available)
    if not configs:
        raise UIUnavailableError(translator.text("error.no_config"))

    ensure_application(qt_widgets, language=translator.language)
    jieba_configs = {
        base: plugin
        for base, plugin in JIEBA_CONFIG_BY_BASE.items()
        if plugin in available
    }
    dialog = _ConversionConfigDialog(
        qt_widgets, configs, default_config, jieba_configs, translator=translator,
        jieba_probe=jieba_probe, initial_options=initial_options,
        metadata_available=metadata_available, nav_available=nav_available,
        services=services, ui_preferences=ui_preferences,
    )
    exec_dialog(dialog.dialog)
    if callable(save_ui_preferences):
        state = {**dict(ui_preferences or {}), **dialog.options_panel.ui_state()}
        size = getattr(dialog.dialog, "size", None)
        size = size() if callable(size) else None
        if size is not None:
            width, height = getattr(size, "width", None), getattr(size, "height", None)
            if callable(width) and callable(height):
                state["conversion_dialog_size"] = [int(width()), int(height())]
        save_ui_preferences(state)
    return ConfigOutcome(dialog.action, dialog.selected_config)


def choose_scope(
    adapter: Any,
    *,
    initial_language: str = "en",
    notice=(),
    initial_selection: TargetSelection | None = None,
    checkpoint_notice_enabled: bool = False,
    hide_checkpoint_notice=None,
    translator: Translator | None = None,
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
    dialog = _ScopeDialog(
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
        checkpoint_notice_enabled=checkpoint_notice_enabled,
        hide_checkpoint_notice=hide_checkpoint_notice,
    )
    exec_dialog(dialog.dialog)
    if not dialog.accepted:
        return ScopeOutcome(
            False, None, dialog.language, dialog.checkpoint_notice_shown)
    translator.set_language(dialog.language)
    selection = resolve_target_selection(
        inventory,
        dialog.scope,
        dialog.spine_ids if dialog.scope is Scope.SPINE else dialog.selected_ids(),
    )
    return ScopeOutcome(
        True, selection, dialog.language, dialog.checkpoint_notice_shown)


def create_progress_reporter(
    total: int, parent: Any = None, *, translator: Translator | None = None,
) -> ProgressReporter:
    """Create a progress reporter using Sigil's already available Qt runtime."""

    translator = translator or Translator("en")
    qt_widgets = _load_ui_qt(translator)
    ensure_application(qt_widgets, language=translator.language)
    return ProgressReporter(qt_widgets, total, parent, translator)


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


def _ordered_scope_inventory(
    inventory: Sequence[TextFile], spine_ids: Sequence[str]
) -> Tuple[TextFile, ...]:
    """Show spine resources in reading order and other XHTML paths afterward."""

    spine_order = {file_id: index for index, file_id in enumerate(spine_ids)}
    return tuple(sorted(
        inventory,
        key=lambda item: (
            0 if item.file_id in spine_order else 1,
            spine_order.get(item.file_id, 0),
            "" if item.file_id in spine_order else item.href,
        ),
    ))


def show_preview(
    planned: Sequence[PlannedDocument], *, translator: Translator | None = None,
    services: Any = None,
) -> PreviewOutcome:
    """Show a preview and return the sessions containing user decisions."""

    translator = translator or Translator("en")
    qt_widgets = _load_ui_qt(translator)
    previews = tuple(PreviewSession(item.plan) for item in planned)
    ensure_application(qt_widgets, language=translator.language)
    dialog = _PreviewDialog(qt_widgets, planned, previews, translator, services)
    exec_dialog(dialog.dialog)
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
    return_to_scope: bool = False,
    diagnostics=(),
    report_text: str | None = None,
    translator: Translator | None = None,
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
    rows = (
        translator.text("result.row.scanned", count=max(int(files_scanned), 0)),
        translator.text(
            "result.row.written", files=max(int(files_changed), 0),
            accepted=max(int(accepted_changes), 0), skipped=max(int(skipped_changes), 0)),
        translator.text(
            "result.row.unwritten", files=not_written,
            unchanged=max(int(files_without_changes), 0)),
    )
    if status == "partial_failure":
        status_line = translator.text("result.status.partial", file=failed_file or "?")
        method = getattr(qt_widgets.QMessageBox, "warning")
    elif status == "cancelled":
        status_line = translator.text("result.status.cancelled")
        method = getattr(qt_widgets.QMessageBox, "information")
    elif accepted_changes == 0 and skipped_changes:
        status_line = translator.text("result.status.skipped")
        method = getattr(qt_widgets.QMessageBox, "information")
    elif accepted_changes == 0:
        status_line = translator.text("result.status.noop")
        method = getattr(qt_widgets.QMessageBox, "information")
    else:
        status_line = translator.text("result.status.success")
        method = getattr(qt_widgets.QMessageBox, "information")
    message = status_line + "\n\n" + "\n".join(rows)
    if status == "success" and accepted_changes > 0:
        message += "\n\n" + translator.text("result.save_reminder")
    diagnostics = tuple(diagnostics)
    if diagnostics:
        rows = []
        for item in diagnostics:
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                file_name, code = item[:2]
                row = f"{file_name}: {diagnostic_summary(translator, str(code))}"
                rows.append(row)
            else:
                rows.append(str(item))
        message += "\n\n" + translator.text("result.invalid_sources") + "\n" + "\n".join(rows)
    if return_to_scope or report_text:
        box = qt_widgets.QMessageBox()
        box.setWindowTitle(translator.text("app.title"))
        box.setText(message)
        back = None
        if return_to_scope:
            back = box.addButton(
                translator.text("result.back_to_scope"), qt_widgets.QMessageBox.ActionRole)
        view_report = None
        if report_text:
            view_report = box.addButton(
                translator.text("result.view_report"), qt_widgets.QMessageBox.ActionRole)
        close = box.addButton(translator.text("common.close"), qt_widgets.QMessageBox.AcceptRole)
        box.setDefaultButton(close)
        box.setEscapeButton(close)
        while True:
            exec_dialog(box)
            clicked = box.clickedButton()
            if view_report is not None and clicked is view_report:
                _show_report_text(qt_widgets, report_text, translator)
                continue
            return "back_to_scope" if back is not None and clicked is back else "close"
    method(None, translator.text("app.title"), message)
    return None


def _show_report_text(qt_widgets, report_text: str, translator: Translator) -> None:
    dialog = qt_widgets.QDialog()
    dialog.setWindowTitle(translator.text("result.view_report"))
    dialog.resize(760, 560)
    layout = qt_widgets.QVBoxLayout(dialog)
    view = qt_widgets.QPlainTextEdit()
    view.setReadOnly(True)
    view.setPlainText(report_text)
    layout.addWidget(view)
    close = qt_widgets.QPushButton(translator.text("common.close"))
    close.clicked.connect(dialog.accept)
    layout.addWidget(close)
    exec_dialog(dialog)


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
    dialog.setWindowTitle(translator.text("error.title"))
    layout = qt_widgets.QVBoxLayout(dialog)
    message_key = {
        "VERIFY_FAILED": "error.verify_failed",
        "SOURCE_CHANGED": "error.source_changed",
        "SETTINGS_CHANGED": "error.settings_changed",
        "GROUP_PARTIAL": "error.group_partial",
    }.get(kind, "error.unexpected")
    message = qt_widgets.QLabel(summary if summary is not None else translator.text(message_key))
    message.setWordWrap(True)
    layout.addWidget(message)
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



def _recovery_notice_text(kind: str, value: str, translator: Translator) -> str:
    key = {
        "preferences_corrupt": "recovery.preferences_corrupt",
        "preferences_future_schema": "recovery.preferences_future_schema",
        "profile_recovered": "recovery.profile_recovered",
        "profile_future_schema": "recovery.profile_future_schema",
        "rulesets_missing": "recovery.rulesets_missing",
        "rulesets_future_schema": "recovery.rulesets_future_schema",
        "rulesets_recovered": "recovery.rulesets_recovered",
    }.get(kind, "recovery.generic")
    return translator.text(key, value=value)


def _guarded_preview_dialog(qt_widgets, guard):
    base_dialog = qt_widgets.QDialog

    class GuardedPreviewDialog(base_dialog):
        def reject(self):
            if guard():
                super().reject()

    return GuardedPreviewDialog()


_PREVIEW_COLUMNS = (
    "status",
    "file",
    "change",
    "source",
    "target",
    "category",
    "risk",
)


def _single_line(value: object) -> str:
    return str(value).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "↵").replace("\t", "⇥")


def _format_change_row(change, href_by_id, translator, *, trim_context: bool) -> Tuple[str, ...]:
    before = _single_line(getattr(change, "text_context_before", ""))
    after = _single_line(getattr(change, "text_context_after", ""))
    if trim_context:
        before = f"…{before[-12:]}" if len(before) > 12 else before
        after = f"{after[:12]}…" if len(after) > 12 else after
    source_text = _single_line(unescape(change.source))
    target_text = _single_line(unescape(change.target))
    source = f"{before}【{source_text}】{after}"
    target = f"{before}【{target_text}】{after}"
    category = translator.text(f"preview.category_value.{change.category}")
    risk = translator.text(f"preview.risk_value.{change.risk.lower()}")
    href = str(
        translator.text("preview.file.metadata")
        if change.document_kind == "metadata"
        else href_by_id.get(change.file_id, change.file_id)
    )
    file_name = href.rsplit("/", 1)[-1] if change.document_kind != "metadata" else href
    return (file_name, f"{source_text} → {target_text}", source, target, category, risk)


def format_change_row(change, href_by_id, translator) -> Tuple[str, ...]:
    """Return concise, plain, localized display values for one preview table row."""

    return _format_change_row(change, href_by_id, translator, trim_context=True)


class _PreviewTableData:
    """Qt-independent row formatting and filtering boundary for preview UI."""

    def __init__(self, entries, href_by_id, translator, group_stats=None, display_cache=None):
        self.entries = tuple(entries)
        self.href_by_id = href_by_id
        self.translator = translator
        self.group_stats = group_stats or {}
        self.display_cache = display_cache if display_cache is not None else {}

    def _status(self, preview, change):
        decision = preview.decision(change.change_id)
        if decision is None:
            return self.translator.text("preview.status.pending")
        if decision.value.startswith("accept"):
            return self.translator.text("preview.status.accepted")
        return self.translator.text("preview.status.skipped")

    def _format(self, row: int) -> Tuple[str, ...]:
        _preview, change = self.entries[row]
        values = list(format_change_row(change, self.href_by_id, self.translator))
        if change.group_id and change.group_id in self.group_stats:
            count, files = self.group_stats[change.group_id]
            values[4] += " — " + self.translator.text(
                "preview.group_row_marker", count=count, files=files)
        return tuple(values)

    def tooltip_values(self, row: int) -> Tuple[str, ...]:
        _preview, change = self.entries[row]
        values = _format_change_row(
            change, self.href_by_id, self.translator, trim_context=False)
        if change.group_id and change.group_id in self.group_stats:
            count, files = self.group_stats[change.group_id]
            values = (*values[:4], values[4] + " — " + self.translator.text(
                "preview.group_row_marker", count=count, files=files), values[5])
        href = str(
            self.translator.text("preview.file.metadata")
            if change.document_kind == "metadata"
            else self.href_by_id.get(change.file_id, change.file_id)
        )
        return (self._status(*self.entries[row]), href, *values[1:])

    def row_count(self) -> int:
        return len(self.entries)

    def row_values(self, row: int) -> Tuple[str, ...]:
        preview, change = self.entries[row]
        values = self.display_cache.get(change.change_id)
        if values is None:
            values = self._format(row)
            self.display_cache[change.change_id] = values
        return (self._status(preview, change), *values)


def _create_preview_table_model(
    qt_widgets, entries, href_by_id, group_stats=None, translator: Translator | None = None,
):
    translator = translator or Translator("en")
    qt_core = getattr(qt_widgets, "QtCore", None)
    if qt_core is None:
        raise UIUnavailableError("Qt table model support is unavailable")
    qabstract_model = qt_core.QAbstractTableModel
    qt = getattr(qt_widgets, "Qt", None)
    gui = getattr(qt_widgets, "QtGui", None)
    headers = tuple(translator.text(f"preview.column.{name}") for name in _PREVIEW_COLUMNS)
    display_cache = {}

    class PreviewTableModel(qabstract_model):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.rows = _PreviewTableData(
                entries, href_by_id, translator, group_stats, display_cache)

        def rowCount(self, parent=None):
            if parent is not None and parent.isValid():
                return 0
            return self.rows.row_count()

        def columnCount(self, parent=None):
            if parent is not None and parent.isValid():
                return 0
            return len(_PREVIEW_COLUMNS)

        def data(self, index, role=None):
            if not index.isValid():
                return None
            values = self.rows.row_values(index.row())
            display_role = _enum_value(qt, "DisplayRole")
            if role == display_role:
                return values[index.column()]
            if role == _enum_value(qt, "ToolTipRole"):
                tooltips = self.rows.tooltip_values(index.row())
                return tooltips[index.column()]
            if role == _enum_value(qt, "ForegroundRole") and gui is not None:
                palette = None
                parent_method = getattr(self, "parent", None)
                parent = parent_method() if callable(parent_method) else None
                palette_method = getattr(parent, "palette", None)
                if callable(palette_method):
                    palette = palette_method()
                if palette is None:
                    application = getattr(qt_widgets, "QApplication", None)
                    palette_method = getattr(application, "palette", None)
                    if callable(palette_method):
                        palette = palette_method()

                dark_mode = None
                palette_type = getattr(gui, "QPalette", None)
                base_role = _enum_value(palette_type, "Base")
                color_method = getattr(palette, "color", None)
                if base_role is not None and callable(color_method):
                    base_color = color_method(base_role)
                    lightness_method = getattr(base_color, "lightness", None)
                    if callable(lightness_method):
                        dark_mode = lightness_method() < 128
                if dark_mode is None:
                    return None

                colors = (
                    {
                        translator.text("preview.status.accepted"): "#7fd18b",
                        translator.text("preview.status.skipped"): "#b0b0b0",
                        translator.text("preview.status.pending"): "#f0b050",
                    }
                    if dark_mode else
                    {
                        translator.text("preview.status.accepted"): "#1f6f2e",
                        translator.text("preview.status.skipped"): "#5f5f5f",
                        translator.text("preview.status.pending"): "#8a4d00",
                    }
                )
                color = colors.get(values[0]) if index.column() == 0 else None
                return gui.QColor(color) if color else None
            if role == _enum_value(qt, "FontRole") and gui is not None and index.column() == 6:
                entry = self.rows.entries[index.row()]
                if entry[1].risk in {"HIGH", "REVIEW"}:
                    font = gui.QFont()
                    font.setBold(True)
                    return font
            return None

        def headerData(self, section, orientation, role=None):
            if role != _enum_value(qt, "DisplayRole"):
                return None
            horizontal = _enum_value(qt, "Horizontal")
            return headers[section] if orientation == horizontal and 0 <= section < len(headers) else None

        def set_entries(self, next_entries):
            if self.rows.entries is next_entries:
                return
            self.beginResetModel()
            self.rows = _PreviewTableData(
                next_entries, href_by_id, translator, group_stats, display_cache)
            self.endResetModel()

        def refresh(self, rows=None):
            if not self.rowCount() or not self.columnCount():
                return
            if rows is None:
                rows = (None,)
            else:
                rows = tuple(dict.fromkeys(row for row in rows if 0 <= row < self.rowCount()))
            if rows == (None,):
                self.dataChanged.emit(
                    self.index(0, 0), self.index(self.rowCount() - 1, 0))
            else:
                for row in rows:
                    self.dataChanged.emit(self.index(row, 0), self.index(row, 0))

    return PreviewTableModel


class _PreviewDialog:
    def __init__(
        self, qt_widgets: Any, planned, previews: Tuple[PreviewSession, ...],
        translator: Translator, services: Any = None,
    ) -> None:
        self._qt = qt_widgets
        self._translator = translator
        self._services = services
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
        self._href_by_id = {
            item.source.file_id: item.source.href for item in self._planned
        }
        self._kind_by_id = {
            item.source.file_id: item.source.document_kind for item in self._planned
        }
        self._file_order = {
            item.source.file_id: index for index, item in enumerate(self._planned)
        }
        group_entries = {}
        groups_by_file = {}
        for _preview, change in self._entries:
            if change.group_id:
                count, files = group_entries.get(change.group_id, (0, set()))
                files.add(change.file_id)
                group_entries[change.group_id] = (count + 1, files)
                groups_by_file.setdefault(change.file_id, set()).add(change.group_id)
        self._group_ids_by_file = {
            file_id: frozenset(group_ids) for file_id, group_ids in groups_by_file.items()
        }
        self._group_stats = {
            group_id: (count, len(files))
            for group_id, (count, files) in group_entries.items()
        }
        self._recompute_counts()
        self._last_group_feedback = ""
        self._visible_entries_cache = self._entries
        self.applied = False
        self.back_to_settings = False
        self.checkpoint_notice_shown = False
        self._allow_reject = False

        self.dialog = _guarded_preview_dialog(qt_widgets, self._guard_reject)
        self.dialog.setWindowTitle(self._translator.text("preview.title"))
        self.dialog.resize(900, 620)
        self._build()
        self._refresh()
        self.table_view.setFocus()

    def _build(self) -> None:
        qt = self._qt
        layout = qt.QVBoxLayout(self.dialog)

        self.summary = qt.QLabel()
        layout.addWidget(self.summary)
        group_row = qt.QHBoxLayout()
        self.group_guidance = qt.QLabel()
        self.accept_group_button = qt.QPushButton(
            self._translator.text("preview.accept_language_group"))
        self.reject_group_button = qt.QPushButton(
            self._translator.text("preview.skip_language_group"))
        self.accept_group_button.clicked.connect(
            lambda: self._decide_current_file_groups(True))
        self.reject_group_button.clicked.connect(
            lambda: self._decide_current_file_groups(False))
        self.accept_group_button.setVisible(False)
        self.reject_group_button.setVisible(False)
        self.group_guidance.setVisible(False)
        group_row.addWidget(self.group_guidance)
        group_row.addWidget(self.accept_group_button)
        group_row.addWidget(self.reject_group_button)
        layout.addLayout(group_row)

        filter_row = qt.QHBoxLayout()
        self.file_filter = qt.QComboBox()
        self.category_filter = qt.QComboBox()
        self.risk_filter = qt.QComboBox()
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
        self._populate_filter(self.file_filter, self._translator.text("preview.filter_file"),
                              file_values, self._translator)
        self._populate_filter(self.category_filter, self._translator.text("preview.filter_category"),
                              category_values, self._translator)
        self._populate_filter(self.risk_filter, self._translator.text("preview.filter_risk"),
                              risk_values, self._translator)
        adjust_policy = _enum_value(
            qt.QComboBox, "AdjustToMinimumContentsLengthWithIcon")
        for widget in (self.file_filter, self.category_filter, self.risk_filter):
            if adjust_policy is not None:
                set_adjust_policy = getattr(widget, "setSizeAdjustPolicy", None)
                if callable(set_adjust_policy):
                    set_adjust_policy(adjust_policy)
            set_minimum_length = getattr(widget, "setMinimumContentsLength", None)
            if callable(set_minimum_length):
                set_minimum_length(16)
            filter_row.addWidget(widget)
            widget.currentIndexChanged.connect(lambda *_args: self._refresh())
        layout.addLayout(filter_row)

        self.table_view = qt.QTableView()
        self.table_model = _create_preview_table_model(
            qt, self._entries, self._href_by_id, self._group_stats, self._translator)(self.table_view)
        self.table_view.setModel(self.table_model)
        item_view = qt.QAbstractItemView
        self.table_view.setSelectionBehavior(_enum_value(item_view, "SelectRows"))
        self.table_view.setSelectionMode(_enum_value(item_view, "SingleSelection"))
        self.table_view.selectionModel().currentRowChanged.connect(
            lambda current, _previous: self._show_current(current.row()))
        header = self.table_view.horizontalHeader()
        interactive = _enum_value(qt.QHeaderView, "Interactive")
        stretch = _enum_value(qt.QHeaderView, "Stretch")
        if interactive is not None and stretch is not None:
            for column in (0, 1, 2, 5, 6):
                header.setSectionResizeMode(column, interactive)
            for column in (3, 4):
                header.setSectionResizeMode(column, stretch)
        set_precision = getattr(header, "setResizeContentsPrecision", None)
        if callable(set_precision):
            set_precision(50)
        self.table_view.setAlternatingRowColors(True)
        layout.addWidget(self.table_view)
        resize_columns = getattr(self.table_view, "resizeColumnsToContents", None)
        if callable(resize_columns):
            resize_columns()

        self.show_source_context = qt.QCheckBox(
            self._translator.text("preview.show_source_context"))
        self.show_source_context.toggled.connect(self._refresh_current)
        layout.addWidget(self.show_source_context)

        self.detail = qt.QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMinimumHeight(180)
        layout.addWidget(self.detail)

        buttons = qt.QHBoxLayout()
        self.accept_this_button = qt.QPushButton(self._translator.text("preview.accept_this"))
        self.reject_this_button = qt.QPushButton(self._translator.text("preview.skip_this"))
        self.accept_file_button = qt.QPushButton(self._translator.text("preview.accept_file"))
        self.reject_file_button = qt.QPushButton(self._translator.text("preview.skip_file"))
        self.accept_all_button = qt.QPushButton(self._translator.text("preview.accept_all"))
        self.reject_all_button = qt.QPushButton(self._translator.text("preview.skip_all"))
        self.accept_filter_button = qt.QPushButton(self._translator.text("preview.accept_filter"))
        self.reject_filter_button = qt.QPushButton(self._translator.text("preview.skip_filter"))
        self.export_button = qt.QPushButton(self._translator.text("preview.export"))
        self.export_full_diff = qt.QCheckBox(self._translator.text("preview.export_full_diff"))
        self.export_full_diff.setChecked(False)
        self.apply_button = qt.QPushButton(self._translator.text("preview.apply"))
        self.apply_status_label = qt.QLabel()
        self.back_settings_button = qt.QPushButton(self._translator.text("preview.back_settings"))
        self.cancel_button = qt.QPushButton(self._translator.text("common.cancel"))
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
        actions.addWidget(self.apply_status_label)
        actions.addStretch(1)
        for button in (self.back_settings_button, self.cancel_button, self.apply_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        self._disable_default_buttons()

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
        self.export_button.setEnabled(
            getattr(self._services, "export_preview", None) is not None
        )
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
                    "accept_this_button", "reject_this_button", "accept_file_button",
                    "reject_file_button", "accept_all_button", "reject_all_button",
                    "accept_filter_button", "reject_filter_button", "export_button",
                    "apply_button", "back_settings_button", "cancel_button",
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
        context = _enum_value(getattr(self._qt, "Qt", None), "WidgetWithChildrenShortcut")
        self._shortcuts = []
        for sequence, callback in (
            ("A", self._accept_this),
            ("S", self._reject_this),
            ("N", self._next_undecided),
            ("Shift+N", self._previous_undecided),
        ):
            shortcut = shortcut_type(key_sequence(sequence), self.dialog)
            if context is not None:
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
        checkbox = getattr(self, "export_full_diff", None)
        include_full_diff = bool(checkbox is not None and checkbox.isChecked())
        try:
            export(self._planned, self._previews, include_full_diff, self._qt, self.dialog)
        except Exception as error:
            self._qt.QMessageBox.warning(
                self.dialog,
                self._translator.text("preview.export"),
                self._translator.text("preview.export_failed", reason=str(error)),
            )

    @staticmethod
    def _populate_filter(
        combo: Any, label: str, values: Sequence[Tuple[str, str]], translator: Translator,
    ) -> None:
        combo.addItem(f"{label}: {translator.text('preview.filter_all')}", None)
        for display, value in values:
            combo.addItem(str(display), str(value))

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
        if not any((current.file_id, current.category, current.risk, current.rule_source)):
            return self._entries
        return tuple((preview, change) for preview, change in self._entries if current.matches(change))

    @staticmethod
    def _decision_bucket(decision) -> str:
        if decision is None:
            return "undecided"
        return "accepted" if decision.value.startswith("accept") else "rejected"

    def _recompute_counts(self) -> None:
        entries = getattr(self, "_entries", ())
        self._totals = {
            "total": len(entries), "accepted": 0, "rejected": 0, "undecided": 0,
        }
        self._file_filter_counts = {}
        self._accepted_count_by_file = {}
        for preview, change in entries:
            bucket = self._decision_bucket(preview.decision(change.change_id))
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

    def _current_row(self) -> int:
        table = getattr(self, "table_view", None)
        if table is None:
            return -1
        index = table.currentIndex()
        return index.row() if index.isValid() else -1

    def _selected_change_id(self) -> str | None:
        row = self._current_row()
        entries = getattr(self, "_visible_entries_cache", None)
        if entries is None:
            entries = self._visible_entries()
        if 0 <= row < len(entries):
            return entries[row][1].change_id
        return None

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

    def _diagnostics_for_file(self, file_id: str | None = None) -> Tuple[str, ...]:
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

    def _skipped_source_details(self) -> Tuple[str, ...]:
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
                rows.append(f"{href}: {location}")
        return tuple(rows)

    def _refresh(self, *_args, recalculate_counts=False, refresh_statuses=False) -> None:
        if recalculate_counts:
            self._recompute_counts()
        selected_change_id = self._selected_change_id()
        visible_entries = self._visible_entries()
        self._visible_entries_cache = visible_entries
        row = next(
            (index for index, (_preview, change) in enumerate(visible_entries)
             if change.change_id == selected_change_id),
            0 if visible_entries else -1,
        )
        if getattr(self, "table_model", None) is not None:
            prior_entries = self.table_model.rows.entries
            self.table_model.set_entries(visible_entries)
            if refresh_statuses and prior_entries is visible_entries:
                self.table_model.refresh()
            self._set_current_row(row)
        if visible_entries:
            self._show_current(row)
        else:
            self.detail.setPlainText(self._translator.text("preview.no_changes"))
            self._update_group_controls(None)
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
            summary += "\n" + self._translator.text(
                "preview.skipped_sources", files="\n".join(skipped_sources))
        group_feedback = getattr(self, "_last_group_feedback", "")
        if group_feedback:
            summary += "\n" + group_feedback
        self.summary.setText(summary)
        self._refresh_file_filter_counts()
        has_current = bool(getattr(self, "_visible_entries_cache", ()))
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
        accepted_files = self._accepted_count_by_file
        complete = totals["undecided"] == 0
        accepted_count = totals["accepted"]
        if not complete:
            self.apply_button.setText(self._translator.text("preview.apply"))
            status_key = "preview.apply_status_pending"
            status_values = {"count": totals["undecided"]}
        elif accepted_count:
            apply_key = "preview.apply_decisions_one" if len(accepted_files) == 1 else "preview.apply_decisions_many"
            self.apply_button.setText(self._translator.text(
                apply_key, changes=accepted_count,
                files=len(accepted_files)))
            status_key = "preview.apply_status_ready"
            status_values = {}
        else:
            self.apply_button.setText(self._translator.text("preview.apply_no_changes"))
            status_key = "preview.apply_status_none"
            status_values = {}
        status_label = getattr(self, "apply_status_label", None)
        if status_label is not None:
            status_label.setText(self._translator.text(status_key, **status_values))
        self.apply_button.setEnabled(complete)
        set_tooltip = getattr(self.apply_button, "setToolTip", None)
        if callable(set_tooltip):
            set_tooltip("" if complete else self._translator.text("preview.incomplete"))

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
        visible_entries = getattr(self, "_visible_entries_cache", None)
        if visible_entries is None:
            visible_entries = self._visible_entries()
        if row < 0 or row >= len(visible_entries):
            self.detail.clear()
            self._update_group_controls(None)
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
            context_before = _single_line(change.context_before)
            context_after = _single_line(change.context_after)
        else:
            context_before = _single_line(change.text_context_before)
            context_after = _single_line(change.text_context_after)
        source_line = f"{context_before}【{_single_line(unescape(change.source))}】{context_after}"
        target_line = f"{context_before}【{_single_line(unescape(change.target))}】{context_after}"
        group_text = ""
        if change.group_id:
            count, files = getattr(self, "_group_stats", {}).get(change.group_id, (1, 1))
            group_text = "\n" + self._translator.text(
                "preview.group_explanation", count=count, files=files)
        self.detail.setPlainText(
            f"{self._translator.text('preview.rule')}: {change.rule_source}\n"
            f"{self._translator.text('preview.category')}: "
            f"{self._translator.text(f'preview.category_value.{change.category}')}    "
            f"{self._translator.text('preview.risk')}: "
            f"{self._translator.text(f'preview.risk_value.{change.risk.lower()}')}\n"
            f"{self._translator.text('preview.before')}: {source_line}\n"
            f"{self._translator.text('preview.after')}: {target_line}"
            f"{group_text}"
            f"{diagnostic_text}"
        )
        self._update_group_controls(change.file_id)

    def _current_entry(self):
        row = self._current_row()
        visible_entries = getattr(self, "_visible_entries_cache", None)
        if visible_entries is None:
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
            count = self._decide_group(change.group_id, accepted)
            feedback_key = (
                "preview.group_accepted" if accepted else "preview.group_skipped")
            self._last_group_feedback = self._translator.text(
                feedback_key, count=count)
            self._refresh(recalculate_counts=True, refresh_statuses=True)
        else:
            self._last_group_feedback = ""
            row = self._current_row()
            before = preview.decision(change.change_id)
            (preview.accept_this if accepted else preview.reject_this)(change.change_id)
            after = preview.decision(change.change_id)
            self._record_decision_change(change.file_id, before, after)
            self._refresh_current(rows=(row,))
        self._select_next_undecided(change.change_id)

    def _select_next_undecided(self, current_change_id=None, *, direction: int = 1) -> None:
        entries = getattr(self, "_visible_entries_cache", None)
        if entries is None:
            entries = self._visible_entries()
        if not entries:
            return
        current_row = self._current_row()
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
        for preview, change in self._entries:
            if change.group_id == group_id:
                (preview.accept_this if accepted else preview.reject_this)(change.change_id)
                count += 1
        return count

    def _groups_for_file(self, file_id):
        if hasattr(self, "_group_ids_by_file"):
            return self._group_ids_by_file.get(file_id, frozenset())
        return {
            change.group_id
            for _preview, change in self._entries
            if change.file_id == file_id and change.group_id
        }

    def _update_group_controls(self, file_id):
        guidance = getattr(self, "group_guidance", None)
        accept = getattr(self, "accept_group_button", None)
        reject = getattr(self, "reject_group_button", None)
        if guidance is None or accept is None or reject is None:
            return
        visible = bool(self._groups_for_file(file_id))
        guidance.setText(self._translator.text("preview.group_prompt"))
        guidance.setVisible(visible)
        accept.setVisible(visible)
        reject.setVisible(visible)

    def _decide_current_file_groups(self, accepted):
        entry = self._current_entry()
        if entry is None:
            return
        groups = self._groups_for_file(entry[1].file_id)
        count = sum(self._decide_group(group_id, accepted) for group_id in groups)
        if count:
            feedback_key = (
                "preview.group_accepted" if accepted else "preview.group_skipped")
            self._last_group_feedback = self._translator.text(feedback_key, count=count)
        else:
            self._last_group_feedback = ""
        self._refresh(recalculate_counts=True, refresh_statuses=True)

    def _decide_filtered(self, accepted: bool) -> None:
        visible_entries = self._visible_entries()
        groups = {change.group_id for _preview, change in visible_entries if change.group_id}
        for preview, change in visible_entries:
            if not change.group_id:
                (preview.accept_this if accepted else preview.reject_this)(change.change_id)
        group_count = sum(self._decide_group(group_id, accepted) for group_id in groups)
        if group_count:
            feedback_key = (
                "preview.group_accepted" if accepted else "preview.group_skipped")
            self._last_group_feedback = self._translator.text(
                feedback_key, count=group_count)
        else:
            self._last_group_feedback = ""
        self._refresh(recalculate_counts=True, refresh_statuses=True)

    def _refresh_current(self, *, rows=()) -> None:
        row = self._current_row()
        visible_entries = getattr(self, "_visible_entries_cache", None)
        if visible_entries is None:
            visible_entries = self._visible_entries()
        if row < 0 or row >= len(visible_entries):
            self._update_summary()
            return
        if rows and getattr(self, "table_model", None) is not None:
            self.table_model.refresh(rows=rows)
        self._show_current(row)
        self._update_summary()

    def _accept_file(self) -> None:
        entry = self._current_entry()
        if entry is None:
            return
        self._last_group_feedback = ""
        preview = entry[0]
        for change in preview.changes:
            if not change.group_id:
                preview.accept_this(change.change_id)
        self._refresh(recalculate_counts=True, refresh_statuses=True)

    def _reject_file(self) -> None:
        entry = self._current_entry()
        if entry is None:
            return
        self._last_group_feedback = ""
        preview = entry[0]
        for change in preview.changes:
            if not change.group_id:
                preview.reject_this(change.change_id)
        self._refresh(recalculate_counts=True, refresh_statuses=True)

    def _accept_all(self) -> None:
        self._last_group_feedback = ""
        for preview in self._previews:
            preview.accept_all(overwrite=True)
        self._refresh(recalculate_counts=True, refresh_statuses=True)

    def _reject_all(self) -> None:
        self._last_group_feedback = ""
        for preview in self._previews:
            preview.reject_all(overwrite=True)
        self._refresh(recalculate_counts=True, refresh_statuses=True)

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
            return True
        return self._confirm_discard_decisions()

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
        box.setWindowTitle(self._translator.text("preview.discard_title"))
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
        box.setWindowTitle(self._translator.text("preview.checkpoint_title"))
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
        jieba_probe=None,
        initial_options=None,
        metadata_available=True,
        nav_available=True,
        services=None,
        ui_preferences=None,
    ) -> None:
        self._qt = qt_widgets
        self._jieba_configs = jieba_configs
        self._translator = translator
        self._jieba_probe = jieba_probe
        self._ui_preferences = dict(ui_preferences or {})
        self._probe_error = None
        self._probe_state = "not_started"
        self._default_base = BASE_CONFIG_BY_JIEBA.get(default_config, default_config)
        self._preferred_jieba = default_config in BASE_CONFIG_BY_JIEBA
        self._direction_reselected = not self._preferred_jieba
        self._jieba_auto_checked = False
        self._updating_jieba = False
        self.accepted = False
        self.selected_config = None
        self.action = "cancel"
        self.dialog = qt_widgets.QDialog()
        self.dialog.setWindowTitle(self._translator.text("config.title"))
        size = self._ui_preferences.get("conversion_dialog_size")
        if (isinstance(size, (tuple, list)) and len(size) == 2
                and all(isinstance(item, int) and item > 0 for item in size)):
            self.dialog.resize(size[0], size[1])
        else:
            self.dialog.resize(720, 720)
        self.dialog.setMinimumWidth(460)

        layout = qt_widgets.QVBoxLayout(self.dialog)
        label = qt_widgets.QLabel(self._translator.text("config.explanation"))
        label.setWordWrap(True)
        layout.addWidget(label)

        layout.addWidget(qt_widgets.QLabel(self._translator.text("config.direction")))
        self.combo = qt_widgets.QComboBox()
        config_groups = (
            ("general", ("s2t", "t2s")),
            ("regional", ("s2tw", "s2twp", "s2hk", "s2hkp", "tw2s", "tw2sp",
                           "hk2s", "hk2sp", "t2tw", "t2hk", "tw2t", "hk2t")),
            ("japanese", ("t2jp", "jp2t")),
        )
        available = set(configs)
        groups_added = 0
        for _group, group_configs in config_groups:
            group_values = tuple(config for config in group_configs if config in available)
            if not group_values:
                continue
            if groups_added:
                insert_separator = getattr(self.combo, "insertSeparator", None)
                if callable(insert_separator):
                    insert_separator(self.combo.count())
            for config in group_values:
                label = self._translator.text(f"config.{config}")
                self.combo.addItem(label, config)
            groups_added += 1
        layout.addWidget(self.combo)

        self.jieba_status = qt_widgets.QLabel()
        self.jieba_status.setWordWrap(True)
        layout.addWidget(self.jieba_status)
        self.jieba_checkbox = qt_widgets.QCheckBox(self._translator.text("config.jieba"))
        self.jieba_checkbox.setToolTip(self._translator.text("config.jieba_tooltip"))
        layout.addWidget(self.jieba_checkbox)
        self.jieba_details_button = qt_widgets.QPushButton(
            self._translator.text("config.jieba_details"))
        self.jieba_details_button.setEnabled(False)
        self.jieba_details_button.setVisible(False)
        layout.addWidget(self.jieba_details_button)

        from ui.run_options import RunOptionsPanel
        self.options_panel = RunOptionsPanel(
            qt_widgets, translator, layout, initial=initial_options,
            metadata_available=metadata_available, nav_available=nav_available,
            services=services, ui_preferences=self._ui_preferences,
        )
        self.options_panel.bind(self._get_config, self._set_config, self.dialog)

        self.button_layout = qt_widgets.QHBoxLayout()
        self.back_button = qt_widgets.QPushButton(self._translator.text("scope.back"))
        self.cancel_button = qt_widgets.QPushButton(self._translator.text("common.cancel"))
        self.continue_button = qt_widgets.QPushButton(
            self._translator.text("config.continue"))
        self.continue_button.setDefault(True)
        self.button_layout.addWidget(self.back_button)
        self.button_layout.addStretch(1)
        self.button_layout.addWidget(self.cancel_button)
        self.button_layout.addWidget(self.continue_button)
        self.options_panel.tool_layout.addLayout(self.button_layout)
        self.cancel_button.clicked.connect(self.dialog.reject)
        self.cancel_button.clicked.connect(self._stop_probe_timer)
        self.back_button.clicked.connect(self._back_to_scope)
        self.continue_button.clicked.connect(self._accept)
        self.combo.currentIndexChanged.connect(self._direction_changed)
        self.jieba_checkbox.stateChanged.connect(self._update_jieba_state)
        self.jieba_details_button.clicked.connect(self._show_jieba_details)
        selected_index = self.combo.findData(self._default_base)
        if selected_index >= 0:
            self.combo.setCurrentIndex(selected_index)
        self.jieba_checkbox.setChecked(
            default_config in self._jieba_configs.values())
        if self.jieba_checkbox.isChecked():
            self._jieba_auto_checked = True
        if self._jieba_probe is not None:
            self._poll_jieba_probe()
            if self._probe_state == "pending":
                timer_type = getattr(qt_widgets, "QTimer", None)
                if timer_type is not None:
                    self._probe_timer = timer_type(self.dialog)
                    self.dialog.finished.connect(self._stop_probe_timer)
                    self._probe_timer.setInterval(50)
                    self._probe_timer.timeout.connect(self._poll_jieba_probe)
                    self._probe_timer.start()
        else:
            self._probe_state = "available" if self._jieba_configs else "unavailable"
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
        if self._updating_jieba:
            return
        self._updating_jieba = True
        try:
            self._apply_jieba_state()
        finally:
            self._updating_jieba = False

    def _apply_jieba_state(self) -> None:
        base_config = str(self.combo.currentData())
        plugin_config = self._jieba_configs.get(base_config)
        if self._probe_state in {"not_started", "pending"} or plugin_config is None:
            self.jieba_checkbox.setChecked(False)
            self.jieba_checkbox.setEnabled(False)
        else:
            self.jieba_checkbox.setEnabled(True)
        if self._probe_state in {"not_started", "pending"}:
            status = self._translator.text("config.jieba_checking")
        elif self._probe_state == "available":
            status = self._translator.text("config.jieba_available")
        else:
            status = self._translator.text("config.jieba_unavailable")
            if self._preferred_jieba and not self._direction_reselected:
                status += "\n" + self._translator.text("config.jieba_reselect")
        if self._probe_state == "available" and self._preferred_jieba \
                and not self._direction_reselected and base_config == self._default_base \
                and not self._jieba_auto_checked:
            self._jieba_auto_checked = True
            self.jieba_checkbox.setChecked(True)
        if self._probe_error:
            tooltip = self._translator.text(
                "config.jieba_unavailable_tooltip", reason=self._probe_error)
        else:
            tooltip = self._translator.text("config.jieba_tooltip")
        self.jieba_checkbox.setToolTip(tooltip)
        self.jieba_status.setToolTip(tooltip)
        self.jieba_status.setText(status)
        self.jieba_details_button.setEnabled(bool(self._probe_error))
        self.jieba_details_button.setVisible(bool(self._probe_error))
        if self._preferred_jieba and self._probe_state in {"not_started", "pending"}:
            self.continue_button.setEnabled(False)
        elif (self._preferred_jieba and self._probe_state == "unavailable"
              and not self._direction_reselected):
            self.continue_button.setEnabled(False)
        else:
            self.continue_button.setEnabled(True)
        if hasattr(self, "options_panel"):
            self.options_panel.update_enablement(self._get_config())

    def _direction_changed(self, *_args):
        if str(self.combo.currentData()) != self._default_base:
            self._direction_reselected = True
        self._update_jieba_state()

    def _poll_jieba_probe(self):
        state, reason, _elapsed_ms = self._jieba_probe.jieba_probe_state()
        self._probe_state = state
        self._probe_error = reason
        if state == "available":
            available = set(self._jieba_probe.available_configs_nonblocking())
            self._jieba_configs = {
                base: config for base, config in JIEBA_CONFIG_BY_BASE.items()
                if config in available
            }
        elif state == "unavailable":
            self._jieba_configs = {}
        self._update_jieba_state()
        if state != "pending":
            self._stop_probe_timer()

    def _show_jieba_details(self):
        if not self._probe_error:
            return
        self._qt.QMessageBox.information(
            self.dialog,
            self._translator.text("config.jieba_details_title"),
            self._probe_error,
        )

    def _stop_probe_timer(self):
        timer = getattr(self, "_probe_timer", None)
        if timer is not None:
            timer.stop()

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
        preference_options = self.options_panel.preference_values()
        try:
            self.options_panel.validate(config)
            target_language(config, options["language_metadata"], options["language_preset"],
                            options["language_region"])
        except ValueError as exc:
            show_error_details(
                self._qt, self.dialog, self._translator.text("config.title"),
                settings_error_message(self._translator, exc), str(exc),
            )
            return
        self._stop_probe_timer()
        self.selected_config = ConfigurationChoice(
            config, options, preference_options=preference_options)
        self.accepted = True
        self.action = "continue"
        self.dialog.accept()

    def _back_to_scope(self) -> None:
        self.action = "back_to_scope"
        self._stop_probe_timer()
        self.dialog.reject()


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
        nav_id: str | None = None,
        recovery_notices=(),
        initial_scope: Scope | None = None,
        checkpoint_notice_enabled: bool = False,
        hide_checkpoint_notice=None,
    ) -> None:
        self._qt = qt_widgets
        self._inventory = inventory
        self._translator = translator
        self.accepted = False
        self.language = language
        self.ignored_non_xhtml = max(0, ignored_non_xhtml)
        self.spine_ids = tuple(file_id for file_id in spine_ids if file_id)
        self.nav_id = nav_id
        self._manual_selection_ids = set(initial_ids)
        self._single_selected_id = next(iter(initial_ids), None)
        self._recovery_notices = tuple(recovery_notices)
        self._updating_items = False
        self.checkpoint_notice_shown = bool(checkpoint_notice_enabled)
        self._hide_checkpoint_notice_callback = hide_checkpoint_notice
        self._checkpoint_notice_hidden = False
        self.dialog = qt_widgets.QDialog()
        self.dialog.setWindowTitle(translator.text("scope.title"))
        self.dialog.resize(700, 560)
        layout = qt_widgets.QVBoxLayout(self.dialog)
        self.recovery_notice_label = None
        if self._recovery_notices:
            notice_lines = [
                _recovery_notice_text(kind, value, translator)
                for kind, value in self._recovery_notices
            ]
            self.recovery_notice_label = qt_widgets.QLabel("\n".join(notice_lines))
            self.recovery_notice_label.setWordWrap(True)
            layout.addWidget(self.recovery_notice_label)
        self._build_checkpoint_banner(
            qt_widgets, layout, translator, checkpoint_notice_enabled)

        language_row = qt_widgets.QHBoxLayout()
        self.language_label = qt_widgets.QLabel(translator.text("language.label"))
        language_row.addWidget(self.language_label)
        self.language_combo = qt_widgets.QComboBox()
        for code in SUPPORTED_LANGUAGES:
            self.language_combo.addItem(self._translator.text(f"language.name.{code}"), code)
        self.language_combo.setCurrentIndex(max(0, self.language_combo.findData(language)))
        self.language_combo.currentIndexChanged.connect(self._language_changed)
        language_row.addWidget(self.language_combo)
        language_row.addStretch(1)
        layout.addLayout(language_row)

        self.single_radio = qt_widgets.QRadioButton(translator.text("scope.single"))
        self.selected_radio = qt_widgets.QRadioButton(translator.text("scope.selected"))
        self.spine_radio = qt_widgets.QRadioButton(translator.text("scope.spine"))
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
        self.filter_edit.returnPressed.connect(self._focus_first_visible_item)
        layout.addWidget(self.filter_edit)
        self.guide_label = qt_widgets.QLabel(translator.text("scope.selection_guide"))
        self.guide_label.setWordWrap(True)
        self.guide_label.setVisible(not bool(initial_ids))
        layout.addWidget(self.guide_label)
        self.list_widget = qt_widgets.QListWidget()
        layout.addWidget(self.list_widget)
        action_row = qt_widgets.QHBoxLayout()
        self.select_visible = qt_widgets.QPushButton(translator.text("scope.select_visible"))
        self.clear_visible = qt_widgets.QPushButton(translator.text("scope.clear_visible"))
        self.select_visible.setAutoDefault(False)
        self.clear_visible.setAutoDefault(False)
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
        self.cancel_button.setAutoDefault(False)
        set_default = getattr(self.analyze_button, "setDefault", None)
        if callable(set_default):
            set_default(True)
        set_auto_default = getattr(self.analyze_button, "setAutoDefault", None)
        if callable(set_auto_default):
            set_auto_default(False)
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
            label = self._scope_item_label(item)
            row = qt_widgets.QListWidgetItem(label)
            row.setData(qt_widgets.Qt.UserRole, item.file_id)
            row.setFlags(row.flags() | qt_widgets.Qt.ItemIsUserCheckable)
            row.setCheckState(
                qt_widgets.Qt.Checked if item.file_id in initial else qt_widgets.Qt.Unchecked
            )
            self.list_widget.addItem(row)
        self.list_widget.itemChanged.connect(self._item_changed)
        current_row_changed = getattr(self.list_widget, "currentRowChanged", None)
        if current_row_changed is not None:
            current_row_changed.connect(self._current_row_changed)
        if initial_scope is Scope.SINGLE:
            self.single_radio.setChecked(True)
        elif initial_scope is Scope.SELECTED:
            self.selected_radio.setChecked(True)
        elif initial_scope is Scope.SPINE:
            self.spine_radio.setChecked(True)
        elif initial_scope is Scope.ALL_XHTML:
            self.all_radio.setChecked(True)
        elif len(initial_ids) == 1:
            self.single_radio.setChecked(True)
        elif not initial_ids:
            self.selected_radio.setChecked(True)
        self._refresh_enabled()
        self._refresh_count()

    def _focus_first_visible_item(self) -> None:
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            if not item.isHidden():
                self.list_widget.setCurrentRow(row)
                self.list_widget.setFocus()
                return

    def _item_changed(self, _item: Any) -> None:
        """Refresh counts and validity for direct checkbox changes."""
        if self._updating_items:
            return
        if self.selected_radio.isChecked():
            self._manual_selection_ids = set(self._checked_ids())
        elif self.all_radio.isChecked() or self.spine_radio.isChecked():
            self._refresh_mode_items()
        self._refresh_count()
        self._update_analyze_enabled()

    def _current_row_changed(self, row: int) -> None:
        if self.single_radio.isChecked() and row >= 0:
            item = self.list_widget.item(row)
            self._single_selected_id = item.data(self._qt.Qt.UserRole)
        self._refresh_count()
        self._update_analyze_enabled()

    def _language_changed(self) -> None:
        code = str(self.language_combo.currentData())
        self.language = code
        self._translator.set_language(code)
        self.dialog.setWindowTitle(self._translator.text("scope.title"))
        self.language_label.setText(self._translator.text("language.label"))
        self.guide_label.setText(self._translator.text("scope.selection_guide"))
        for row, item in enumerate(self._inventory):
            self.list_widget.item(row).setText(self._scope_item_label(item))
        if self.recovery_notice_label is not None and self.recovery_notice_label.isVisible():
            self.recovery_notice_label.setText("\n".join(
                _recovery_notice_text(kind, value, self._translator)
                for kind, value in self._recovery_notices
            ))
        self.single_radio.setText(self._translator.text("scope.single"))
        self.selected_radio.setText(self._translator.text("scope.selected"))
        self.spine_radio.setText(self._translator.text("scope.spine"))
        self.all_radio.setText(self._translator.text("scope.all"))
        self.filter_edit.setPlaceholderText(self._translator.text("scope.filter"))
        self.select_visible.setText(self._translator.text("scope.select_visible"))
        self.clear_visible.setText(self._translator.text("scope.clear_visible"))
        if self.checkpoint_banner is not None:
            self.checkpoint_notice_label.setText(
                self._translator.text("scope.checkpoint_notice"))
            self.checkpoint_hide_checkbox.setText(
                self._translator.text("scope.checkpoint_hide"))
            self.checkpoint_close_button.setToolTip(
                self._translator.text("scope.checkpoint_close"))
        self.cancel_button.setText(self._translator.text("common.cancel"))
        self.analyze_button.setText(self._translator.text("scope.analyze"))
        self._refresh_count()
        self._update_analyze_enabled()

    def _scope_item_label(self, item: TextFile) -> str:
        label = item.href
        if item.file_id == self.nav_id:
            label += " " + self._translator.text("scope.navigation_suffix")
        return label

    def _checkpoint_notice_preference_changed(self, checked: bool) -> None:
        if not checked or self._checkpoint_notice_hidden:
            return
        self._checkpoint_notice_hidden = True
        if callable(self._hide_checkpoint_notice_callback):
            self._hide_checkpoint_notice_callback()
        if self.checkpoint_banner is not None:
            self.checkpoint_banner.hide()

    def _build_checkpoint_banner(self, qt_widgets, layout, translator, enabled):
        self.checkpoint_banner = None
        if not enabled:
            return
        self.checkpoint_banner = qt_widgets.QWidget()
        checkpoint_layout = qt_widgets.QHBoxLayout(self.checkpoint_banner)
        self.checkpoint_notice_label = qt_widgets.QLabel(
            translator.text("scope.checkpoint_notice"))
        self.checkpoint_notice_label.setWordWrap(True)
        checkpoint_layout.addWidget(self.checkpoint_notice_label, 1)
        self.checkpoint_hide_checkbox = qt_widgets.QCheckBox(
            translator.text("scope.checkpoint_hide"))
        self.checkpoint_hide_checkbox.toggled.connect(
            self._checkpoint_notice_preference_changed)
        checkpoint_layout.addWidget(self.checkpoint_hide_checkbox)
        self.checkpoint_close_button = qt_widgets.QPushButton("×")
        set_auto_default = getattr(self.checkpoint_close_button, "setAutoDefault", None)
        if callable(set_auto_default):
            set_auto_default(False)
        self.checkpoint_close_button.setToolTip(
            translator.text("scope.checkpoint_close"))
        self.checkpoint_close_button.clicked.connect(self.checkpoint_banner.hide)
        checkpoint_layout.addWidget(self.checkpoint_close_button)
        layout.addWidget(self.checkpoint_banner)

    def _checked_ids(self) -> Tuple[str, ...]:
        checked = self._qt.Qt.Checked
        return tuple(
            self.list_widget.item(index).data(self._qt.Qt.UserRole)
            for index in range(self.list_widget.count())
            if self.list_widget.item(index).checkState() == checked
        )

    def selected_ids(self) -> Tuple[str, ...]:
        if self.single_radio.isChecked():
            row = self.list_widget.currentRow()
            if row < 0:
                return ()
            item = self.list_widget.item(row)
            return (item.data(self._qt.Qt.UserRole),)
        if self.all_radio.isChecked():
            return tuple(item.file_id for item in self._inventory)
        if self.spine_radio.isChecked():
            available = {item.file_id for item in self._inventory}
            return tuple(file_id for file_id in self.spine_ids if file_id in available)
        return tuple(item.file_id for item in self._inventory
                     if item.file_id in self._manual_selection_ids)

    def _refresh_list(self) -> None:
        query = self.filter_edit.text().strip().lower()
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            item.setHidden(bool(query) and query not in item.text().lower())
        self._refresh_count()

    def _set_visible(self, checked: bool) -> None:
        if not self.selected_radio.isChecked():
            return
        state = self._qt.Qt.Checked if checked else self._qt.Qt.Unchecked
        self.list_widget.blockSignals(True)
        try:
            for index in range(self.list_widget.count()):
                item = self.list_widget.item(index)
                if not item.isHidden():
                    item.setCheckState(state)
        finally:
            self.list_widget.blockSignals(False)
        self._manual_selection_ids = set(self._checked_ids())
        self._refresh_count()
        self._update_analyze_enabled()

    def _refresh_count(self) -> None:
        total = self.list_widget.count()
        selected = len(self.selected_ids()) if hasattr(self, "list_widget") else 0
        visible = sum(not self.list_widget.item(index).isHidden()
                      for index in range(total))
        if self.single_radio.isChecked():
            selected_id = next(iter(self.selected_ids()), None)
            selected_file = next(
                (item.href for item in self._inventory if item.file_id == selected_id), None)
            self.count_label.setText(
                self._translator.text("scope.selected_file", file=selected_file)
                if selected_file else self._translator.text("scope.none")
            )
        else:
            self.count_label.setText(self._translator.text(
                "scope.selection_count", selected=selected, total=total, visible=visible))
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
        custom = self.selected_radio.isChecked()
        self.filter_edit.setEnabled(True)
        self.list_widget.setEnabled(True)
        self.select_visible.setEnabled(custom)
        self.clear_visible.setEnabled(custom)
        self.spine_radio.setEnabled(bool(self.spine_ids))
        self._refresh_mode_items()
        self._refresh_count()
        self._update_analyze_enabled()

    def _refresh_mode_items(self) -> None:
        if not hasattr(self, "list_widget"):
            return
        mode = ("single" if self.single_radio.isChecked() else
                "spine" if self.spine_radio.isChecked() else
                "all" if self.all_radio.isChecked() else "selected")
        qt = self._qt.Qt
        checkable = getattr(qt, "ItemIsUserCheckable", 16)
        self._updating_items = True
        self.list_widget.blockSignals(True)
        try:
            available = {item.file_id for item in self._inventory}
            fixed_ids = (set(self.spine_ids) & available if mode == "spine" else
                         available if mode == "all" else set())
            if mode == "single":
                if self._single_selected_id not in available:
                    self._single_selected_id = next(
                        (file_id for file_id in self._inventory_ids()
                         if file_id in self._manual_selection_ids), None)
                for index in range(self.list_widget.count()):
                    item = self.list_widget.item(index)
                    item.setFlags(item.flags() & ~checkable)
                    item.setData(qt.CheckStateRole, None)
                row = next((index for index in range(self.list_widget.count())
                            if self.list_widget.item(index).data(qt.UserRole)
                            == self._single_selected_id), -1)
                self.list_widget.setCurrentRow(row)
            else:
                for index in range(self.list_widget.count()):
                    item = self.list_widget.item(index)
                    item.setFlags(item.flags() | checkable)
                    file_id = item.data(qt.UserRole)
                    checked = (file_id in self._manual_selection_ids if mode == "selected"
                               else file_id in fixed_ids)
                    item.setCheckState(qt.Checked if checked else qt.Unchecked)
            self.guide_label.setVisible(
                mode in {"selected", "single"} and not self._manual_selection_ids)
        finally:
            self.list_widget.blockSignals(False)
            self._updating_items = False

    def _inventory_ids(self) -> Tuple[str, ...]:
        return tuple(item.file_id for item in self._inventory)

    def _update_analyze_enabled(self) -> None:
        if not hasattr(self, "analyze_button"):
            return
        count = len(self.selected_ids())
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
