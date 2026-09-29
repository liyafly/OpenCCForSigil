"""Minimal Preview UI for the first interactive conversion phase."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter
from dataclasses import dataclass
from html import unescape
import re
from typing import Any, Sequence, Tuple

from core.preview import (
    PreviewDecision,
    PreviewFilter,
    PreviewGroupKind,
    PreviewSession,
    preview_group_kind,
)
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
    configuration_label,
    diagnostic_summary,
    plugin_window_title,
    settings_error_message,
    show_error_details,
)
from ui.window_state import restore_window_size, save_window_size
from ui.run_summary import run_summary_data
from ui.preview_batch import plan_batch_decision

_DECISION_VALUES = tuple(PreviewDecision)
_DECISION_TO_CODE = {decision: index + 1
                     for index, decision in enumerate(_DECISION_VALUES)}
_LINE_BREAK = re.compile(r"\r\n?|\n")


class UIUnavailableError(RuntimeError):
    """Raised when Sigil's bundled Qt runtime cannot be imported."""


@dataclass(frozen=True)
class PreviewOutcome:
    accepted: bool
    previews: Tuple[PreviewSession, ...]
    back_to_settings: bool = False
    checkpoint_notice_shown: bool = False


@dataclass(frozen=True, slots=True)
class _DecisionHistoryChange:
    file_id: str
    change_id: str
    before: PreviewDecision | None
    after: PreviewDecision | None


@dataclass(frozen=True, slots=True)
class _DecisionHistoryOperation:
    sequence: int
    changes: Tuple[_DecisionHistoryChange, ...]




@dataclass(frozen=True, slots=True)
class _ScopedBulkDecisionHistoryOperation:
    sequence: int
    before_decisions: Tuple[Tuple[str, Tuple[str, ...], bytes], ...]
    after: PreviewDecision
    change_count: int

    @property
    def changes(self):
        return range(self.change_count)


@dataclass(frozen=True, slots=True)
class _DiagnosticRecord:
    file_id: str
    href: str
    code: str
    name: str
    description: str
    location: str
    excerpt: str
    related_changes: Tuple[Tuple[str, str], ...]


@dataclass(frozen=True)
class ScopeOutcome:
    accepted: bool
    selection: TargetSelection | None
    language: str
    configuration: object | None = None


class ProgressReporter:
    """A lightweight progress view driven by workflow file boundaries."""

    def __init__(
        self, qt_widgets: Any, total: int, parent: Any = None,
        translator: Translator | None = None,
        ui_preferences=None,
        save_ui_preferences=None,
    ) -> None:
        self._qt = qt_widgets
        self._translator = translator or Translator("en")
        self._save_ui_preferences = save_ui_preferences
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
        self.dialog.setWindowTitle(plugin_window_title(
            self._translator, self._translator.text("progress.title")))
        restore_window_size(
            self.dialog, ui_preferences, "progress_dialog_size", (520, 180))
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
        set_tooltip = getattr(self.dialog, "setToolTip", None)
        if callable(set_tooltip):
            set_tooltip(full_name)
        if len(full_name) <= 55:
            return full_name
        left_count = 27
        right_count = 27
        return f"{full_name[:left_count]}…{full_name[-right_count:]}"

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
        save_window_size(
            self.dialog, "progress_dialog_size", self._save_ui_preferences)
        self.dialog.close()

    def _process_events(self) -> None:
        process_events = getattr(self._qt.QApplication, "processEvents", None)
        if callable(process_events):
            process_events()


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
    nav_available=True,
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
        metadata_available=metadata_available, nav_available=nav_available,
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
        nav_available_now = bool(nav_id and nav_id in selected_ids)
        if config_dialog.options_panel._nav_available != nav_available_now:
            config_dialog.options_panel.set_nav_available(nav_available_now)
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
        elif data["nav_available"] and not data["nav_requested"]:
            details.append(translator.text("scope.run_summary_nav_disabled"))
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
        selected = scope_dialog.selection
        config_dialog.options_panel.set_nav_available(
            bool(nav_id and nav_id in selected.file_ids))
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


def _source_line_starts(source: str) -> Tuple[int, ...]:
    """Index original-source lines, treating CRLF as one newline."""

    return (0, *(match.end() for match in _LINE_BREAK.finditer(source)))


def _line_column_for_offset(starts: Tuple[int, ...], offset: int) -> Tuple[int, int]:
    line_index = max(0, bisect_right(starts, offset) - 1)
    return line_index + 1, offset - starts[line_index] + 1


def _index_change_spans(file_id: str, changes: Tuple[Any, ...]):
    """Index eligible change spans while retaining plan order for review rows."""

    indexed = []
    for original_index, change in enumerate(changes):
        if isinstance(change, TokenChange):
            if change.file_id != file_id:
                continue
            change_span = change.span
            change_start = change_span.start
            change_end = change_span.end
        else:
            change_span = getattr(change, "span", None)
            change_start = getattr(change_span, "start", None)
            change_end = getattr(change_span, "end", None)
            if (getattr(change, "file_id", file_id) != file_id
                    or not isinstance(change_start, int)
                    or not isinstance(change_end, int)):
                continue
        if not isinstance(change_start, int) or not isinstance(change_end, int):
            continue
        indexed.append((change_start, change_end, original_index))
    indexed.sort()
    starts = [start for start, _end, _original_index in indexed]
    prefix_max_end = []
    maximum_end = None
    for _start, end, _original_index in indexed:
        if maximum_end is None or end > maximum_end:
            maximum_end = end
        prefix_max_end.append(maximum_end)
    return indexed, starts, prefix_max_end


def _diagnostic_excerpt(
    source: str, start: int | None, end: int | None,
    line: int | None, column: int | None, starts: Tuple[int, ...],
) -> str:
    if not source:
        return ""
    if start is None or end is None or not (0 <= start <= end <= len(source)):
        if line is None or column is None or line < 1 or column < 1:
            return ""
        if line - 1 >= len(starts):
            return ""
        start = min(starts[line - 1] + column - 1, len(source))
        end = start
    # Keep the locator compact even when a diagnostic covers a whole block.
    visible_end = min(end, start + 72)
    before = source[max(0, start - 48):start]
    selected = source[start:visible_end]
    after = source[visible_end:min(len(source), visible_end + 48)]
    marker = selected if selected else "|"
    return f"…{before}【{marker}】{after}…"


def _diagnostic_record_count(planned_documents: Sequence[PlannedDocument]) -> int:
    """Count unique diagnostic rows without building their display content."""

    seen = set()
    for planned in planned_documents:
        source_document = getattr(planned, "source", None)
        plan = getattr(planned, "plan", None)
        if plan is None:
            continue
        file_id = str(
            getattr(source_document, "file_id", "")
            or getattr(plan, "file_id", "")
        )
        for diagnostic in getattr(plan, "diagnostics", ()) or ():
            code = str(getattr(diagnostic, "code", "") or "")
            if not code:
                continue
            span = getattr(diagnostic, "span", None)
            raw_start = getattr(span, "start", None)
            raw_end = getattr(span, "end", None)
            start = raw_start if isinstance(raw_start, int) and not isinstance(raw_start, bool) else None
            end = raw_end if isinstance(raw_end, int) and not isinstance(raw_end, bool) else None
            span_key = (start, end) if start is not None and end is not None else None
            identity = ((file_id, code, span_key,
                         str(getattr(diagnostic, "message", "") or ""))
                        if code == "REGEX_ZERO_WIDTH_SKIPPED"
                        else (file_id, code, span_key))
            seen.add(identity)
    return len(seen)


def _diagnostic_records(
    planned_documents: Sequence[PlannedDocument], translator: Translator,
) -> Tuple[_DiagnosticRecord, ...]:
    """Build review rows only from the immutable plan and source snapshot."""

    records = []
    seen = set()
    for planned in planned_documents:
        source_document = getattr(planned, "source", None)
        plan = getattr(planned, "plan", None)
        if plan is None:
            continue
        file_id = str(
            getattr(source_document, "file_id", "")
            or getattr(plan, "file_id", "")
        )
        href = str(getattr(source_document, "href", "") or file_id)
        source_value = getattr(source_document, "source", None)
        has_source = isinstance(source_value, str)
        source = source_value if has_source else ""
        line_starts = None

        def get_line_starts():
            nonlocal line_starts
            if line_starts is None:
                line_starts = _source_line_starts(source)
            return line_starts

        changes = tuple(getattr(plan, "changes", ()) or ())
        change_index = None
        for diagnostic in getattr(plan, "diagnostics", ()) or ():
            code = str(getattr(diagnostic, "code", "") or "")
            if not code:
                continue
            span = getattr(diagnostic, "span", None)
            raw_start = getattr(span, "start", None)
            raw_end = getattr(span, "end", None)
            start = raw_start if isinstance(raw_start, int) and not isinstance(raw_start, bool) else None
            end = raw_end if isinstance(raw_end, int) and not isinstance(raw_end, bool) else None
            span_key = (start, end) if start is not None and end is not None else None
            message = str(getattr(diagnostic, "message", "") or "")
            identity = ((file_id, code, span_key, message)
                        if code == "REGEX_ZERO_WIDTH_SKIPPED"
                        else (file_id, code, span_key))
            if identity in seen:
                continue
            seen.add(identity)

            line = getattr(diagnostic, "line", None)
            column = getattr(diagnostic, "column", None)
            if not (isinstance(line, int) and line > 0
                    and isinstance(column, int) and column > 0):
                line = column = None
                if has_source and start is not None and 0 <= start <= len(source):
                    line, column = _line_column_for_offset(get_line_starts(), start)
            if line is None or column is None:
                location = translator.text("preview.diagnostic_position_unavailable")
            else:
                location = translator.text(
                    "preview.invalid_source_location", line=line, column=column)

            related = []
            if (start is not None and end is not None and 0 <= start <= end <= len(source)):
                if change_index is None:
                    change_index = _index_change_spans(file_id, changes)
                indexed, starts, prefix_max_end = change_index
                lo = bisect_left(prefix_max_end, start)
                hi = bisect_right(starts, end)
                related_hits = []
                for change_start, change_end, original_index in indexed[lo:hi]:
                    change = changes[original_index]
                    if code == "INLINE_BOUNDARY":
                        # The boundary span contains markup, while the affected
                        # text changes sit exactly on either side. The planner
                        # uses these same endpoints when it raises their risk.
                        overlaps = change_end == start or change_start == end
                    else:
                        overlaps = (
                            change_start <= start <= change_end
                            if start == end
                            else change_start < end and start < change_end
                        )
                    if overlaps:
                        identity = (file_id, str(getattr(change, "change_id", "")))
                        related_hits.append((original_index, identity))
                related_seen = set()
                for _original_index, identity in sorted(related_hits):
                    if identity not in related_seen:
                        related_seen.add(identity)
                        related.append(identity)
            diagnostic_name = translator.text(f"diagnostic.name.{code}", code=code)
            if diagnostic_name == f"diagnostic.name.{code}":
                diagnostic_name = translator.text("diagnostic.name.unknown", code=code)
            description = diagnostic_summary(translator, code, 1)
            if code == "REGEX_ZERO_WIDTH_SKIPPED":
                match = re.match(r"rule (\S+): skipped (\d+) ", message)
                if match:
                    description = translator.text(
                        "rules.zero_width_skipped",
                        id=match.group(1), count=int(match.group(2)))
            if (source and (start is None or end is None
                            or not (0 <= start <= end <= len(source)))
                    and line is not None and column is not None):
                excerpt_starts = get_line_starts()
            else:
                excerpt_starts = line_starts or ()
            records.append(_DiagnosticRecord(
                file_id=file_id,
                href=href,
                code=code,
                name=diagnostic_name,
                description=description,
                location=location,
                excerpt=_diagnostic_excerpt(source, start, end, line, column, excerpt_starts),
                related_changes=tuple(related),
            ))
    return tuple(records)


class _DiagnosticPanel:
    """Read-only, filterable diagnostics backed by frozen source snapshots."""

    def __init__(
        self, qt: Any, records: Sequence[_DiagnosticRecord], translator: Translator,
        on_related_change=None,
    ) -> None:
        self._qt = qt
        self._records = tuple(records)
        self._translator = translator
        self._on_related_change = on_related_change
        self.widget = qt.QWidget()
        layout = qt.QVBoxLayout(self.widget)

        self.toggle = qt.QToolButton()
        self.toggle.setText(translator.text(
            "preview.diagnostics_count", count=len(self._records)))
        self.toggle.setCheckable(True)
        self.toggle.setAccessibleName(translator.text("a11y.preview.diagnostics"))
        self.toggle.setToolButtonStyle(_enum_value(qt.Qt, "ToolButtonTextBesideIcon"))
        layout.addWidget(self.toggle)

        self.content = qt.QWidget()
        content_layout = qt.QVBoxLayout(self.content)
        filter_row = qt.QHBoxLayout()
        self.file_filter = qt.QComboBox()
        self.code_filter = qt.QComboBox()
        self._populate_filter(
            self.file_filter,
            translator.text("preview.filter_file"),
            tuple((record.href, record.file_id)
                  for record in self._unique_by_value("file_id")),
            translator,
        )
        self._populate_filter(
            self.code_filter,
            translator.text("preview.diagnostic_code_filter"),
            tuple((record.name, record.code)
                  for record in self._unique_by_value("code")),
            translator,
        )
        for combo in (self.file_filter, self.code_filter):
            combo.setSizeAdjustPolicy(
                _enum_value(qt.QComboBox, "AdjustToMinimumContentsLengthWithIcon"))
            combo.setMinimumContentsLength(10)
            filter_row.addWidget(combo)
            combo.currentIndexChanged.connect(self._refresh)
        self.count_label = qt.QLabel()
        filter_row.addWidget(self.count_label)
        content_layout.addLayout(filter_row)

        self.table = qt.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels((
            translator.text("preview.column.file"),
            translator.text("preview.diagnostic_column.code"),
            translator.text("preview.diagnostic_column.position"),
            translator.text("preview.diagnostic_column.description"),
        ))
        self.table.setSelectionBehavior(
            _enum_value(qt.QAbstractItemView, "SelectRows"))
        self.table.setSelectionMode(
            _enum_value(qt.QAbstractItemView, "SingleSelection"))
        self.table.setEditTriggers(_enum_value(qt.QAbstractItemView, "NoEditTriggers"))
        self.table.setAccessibleName(translator.text("a11y.preview.diagnostics"))
        header = self.table.horizontalHeader()
        interactive = _enum_value(qt.QHeaderView, "Interactive")
        stretch = _enum_value(qt.QHeaderView, "Stretch")
        if interactive is not None and stretch is not None:
            for column in (0, 1, 2):
                header.setSectionResizeMode(column, interactive)
            header.setSectionResizeMode(3, stretch)
        self.table.currentCellChanged.connect(self._row_selected)
        self.table.cellClicked.connect(self._row_selected)
        content_layout.addWidget(self.table)

        self.context = qt.QPlainTextEdit()
        self.context.setReadOnly(True)
        self.context.setAccessibleName(translator.text("a11y.preview.diagnostic_context"))
        self.context.setMinimumHeight(64)
        content_layout.addWidget(self.context)
        layout.addWidget(self.content)
        self.toggle.toggled.connect(self.set_expanded)
        self.set_expanded(False)
        self._visible_records: Tuple[_DiagnosticRecord, ...] = ()
        self._refresh()

    def _unique_by_value(self, attribute: str) -> Tuple[_DiagnosticRecord, ...]:
        selected = set()
        result = []
        for record in self._records:
            value = getattr(record, attribute)
            if value in selected:
                continue
            selected.add(value)
            result.append(record)
        return tuple(result)

    @staticmethod
    def _populate_filter(combo, label, values, translator) -> None:
        combo.addItem(
            f"{label}{translator.text('common.label_separator')}"
            f"{translator.text('preview.filter_all')}", None)
        for display, value in values:
            combo.addItem(str(display), str(value))

    def set_expanded(self, expanded: bool) -> None:
        expanded = bool(expanded)
        self.content.setVisible(expanded)
        arrow = _enum_value(
            self._qt.Qt, "DownArrow" if expanded else "RightArrow")
        if arrow is not None:
            self.toggle.setArrowType(arrow)
        if self.toggle.isChecked() != expanded:
            blocked = self.toggle.blockSignals(True)
            try:
                self.toggle.setChecked(expanded)
            finally:
                self.toggle.blockSignals(blocked)

    def _refresh(self, *_args) -> None:
        file_id = self.file_filter.currentData()
        code = self.code_filter.currentData()
        records = tuple(
            record for record in self._records
            if (file_id is None or record.file_id == file_id)
            and (code is None or record.code == code)
        )
        self._visible_records = records
        self.count_label.setText(self._translator.text(
            "preview.diagnostics_visible", visible=len(records), total=len(self._records)))
        blocked = self.table.blockSignals(True)
        try:
            self.table.setRowCount(0)
            self.table.setRowCount(len(records))
            qt_user_role = _enum_value(self._qt.Qt, "UserRole")
            for row, record in enumerate(records):
                values = (record.href, record.name, record.location,
                          record.description)
                for column, value in enumerate(values):
                    item = self._qt.QTableWidgetItem(str(value))
                    if column == 0 and qt_user_role is not None:
                        item.setData(qt_user_role, row)
                    self.table.setItem(row, column, item)
            if records:
                self.table.setCurrentCell(0, 0)
        finally:
            self.table.blockSignals(blocked)
        if records:
            self._row_selected(0, navigate=False)
        else:
            self.context.setPlainText(
                self._translator.text("preview.diagnostics_no_matches"))

    def _row_selected(self, row: int, *_args, navigate=True) -> None:
        if row < 0 or row >= len(self._visible_records):
            return
        record = self._visible_records[row]
        lines = [
            f"{self._translator.text('preview.diagnostic_column.code')}"
            f"{self._translator.text('common.label_separator')}{record.name}",
            f"{self._translator.text('preview.diagnostic_column.position')}"
            f"{self._translator.text('common.label_separator')}{record.location}",
            self._translator.text("preview.diagnostic_context_label"),
            record.excerpt or self._translator.text("preview.diagnostic_context_unavailable"),
        ]
        if record.related_changes:
            lines.append(self._translator.text(
                "preview.diagnostic_related_changes", count=len(record.related_changes)))
        self.context.setPlainText("\n".join(lines))
        if (navigate and record.related_changes
                and callable(self._on_related_change)):
            self._on_related_change(record.related_changes[0])


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
        method = getattr(qt_widgets.QMessageBox, "warning")
    elif status == "cancelled":
        status_line = translator.text("result.status.cancelled_unchanged")
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
    warning_type = getattr(style_type, "SP_MessageBoxWarning")
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
    if kind == "profile_recovered":
        return translator.text(
            key, value=value, name=translator.text("profile.default_name"))
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

_MAX_DECISION_HISTORY_OPERATIONS = 100
_MAX_DECISION_HISTORY_CHANGES = 2_000_000


def _single_line(value: object) -> str:
    return str(value).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "↵").replace("\t", "⇥")


def _text_context(change, targets_by_id) -> Tuple[str, str]:
    target = (targets_by_id or {}).get((change.file_id, change.target_id))
    if target is None:
        return "", ""
    text = target.source_text
    start = max(0, min(change.span.start - target.source_start, len(text)))
    end = max(start, min(change.span.end - target.source_start, len(text)))
    before_start = max(0, start - 20)
    after_end = min(len(text), end + 20)
    before = text[before_start:start]
    after = text[end:after_end]
    if before_start:
        before = "…" + before
    if after_end < len(text):
        after += "…"
    return before, after


def _source_context(change, sources_by_id) -> Tuple[str, str]:
    source = (sources_by_id or {}).get(change.file_id, "")
    start = max(0, min(change.span.start, len(source)))
    end = max(start, min(change.span.end, len(source)))
    return source[max(0, start - 32):start], source[end:min(len(source), end + 32)]


def _format_change_row(
    change, href_by_id, translator, *, trim_context: bool, targets_by_id=None,
) -> Tuple[str, ...]:
    before, after = _text_context(change, targets_by_id)
    before = _single_line(before)
    after = _single_line(after)
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


def format_change_row(change, href_by_id, translator, targets_by_id=None) -> Tuple[str, ...]:
    """Return concise, plain, localized display values for one preview table row."""

    return _format_change_row(
        change, href_by_id, translator, trim_context=True, targets_by_id=targets_by_id)


def _group_marker_key(group_id: str) -> str:
    return {
        PreviewGroupKind.LANGUAGE_METADATA: "preview.group_row_marker",
        PreviewGroupKind.RULE_OCCURRENCE: "preview.rule_group_row_marker",
        PreviewGroupKind.LINKED: "preview.linked_group_row_marker",
    }[preview_group_kind(group_id)]


def _group_explanation_key(group_id: str) -> str:
    return {
        PreviewGroupKind.LANGUAGE_METADATA: "preview.group_explanation",
        PreviewGroupKind.RULE_OCCURRENCE: "preview.rule_group_explanation",
        PreviewGroupKind.LINKED: "preview.linked_group_explanation",
    }[preview_group_kind(group_id)]


def _group_feedback_key(group_id_or_kind, accepted: bool) -> str:
    kind = (group_id_or_kind if isinstance(group_id_or_kind, PreviewGroupKind)
            else preview_group_kind(group_id_or_kind))
    if kind is PreviewGroupKind.LANGUAGE_METADATA:
        verb = "accepted" if accepted else "skipped"
        return f"preview.group_{verb}"
    group = "rule_group" if kind is PreviewGroupKind.RULE_OCCURRENCE else "linked_group"
    verb = "accepted" if accepted else "skipped"
    return f"preview.{group}_{verb}"


class _PreviewTableData:
    """Qt-independent row formatting and filtering boundary for preview UI."""

    def __init__(self, entries, href_by_id, translator, group_stats=None, display_cache=None,
                 targets_by_id=None):
        self.entries = tuple(entries)
        self.href_by_id = href_by_id
        self.translator = translator
        self.group_stats = group_stats or {}
        self.display_cache = display_cache if display_cache is not None else {}
        self.targets_by_id = targets_by_id or {}

    def _status(self, preview, change):
        decision = preview.decision(change.change_id)
        if decision is None:
            return self.translator.text("preview.status.pending")
        if decision.value.startswith("accept"):
            return self.translator.text("preview.status.accepted")
        return self.translator.text("preview.status.skipped")

    def _format(self, row: int) -> Tuple[str, ...]:
        _preview, change = self.entries[row]
        values = list(format_change_row(
            change, self.href_by_id, self.translator, self.targets_by_id))
        if change.group_id and change.group_id in self.group_stats:
            count, files = self.group_stats[change.group_id]
            marker_key = _group_marker_key(change.group_id)
            values[4] += " — " + self.translator.text(
                marker_key, count=count, files=files)
        return tuple(values)

    def tooltip_values(self, row: int) -> Tuple[str, ...]:
        _preview, change = self.entries[row]
        values = _format_change_row(
            change, self.href_by_id, self.translator, trim_context=False,
            targets_by_id=self.targets_by_id)
        if change.group_id and change.group_id in self.group_stats:
            count, files = self.group_stats[change.group_id]
            marker_key = _group_marker_key(change.group_id)
            values = (*values[:4], values[4] + " — " + self.translator.text(
                marker_key, count=count, files=files), values[5])
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
    targets_by_id=None,
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
                entries, href_by_id, translator, group_stats, display_cache, targets_by_id)

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
                next_entries, href_by_id, translator, group_stats, display_cache, targets_by_id)
            self.endResetModel()

        def remove_rows(self, ranges):
            entries = self.rows.entries
            for first, last in ranges:
                if first < 0 or last < first or last >= len(entries):
                    continue
                self.beginRemoveRows(qt_core.QModelIndex(), first, last)
                entries = entries[:first] + entries[last + 1:]
                self.rows = _PreviewTableData(
                    entries, href_by_id, translator, group_stats,
                    display_cache, targets_by_id)
                self.endRemoveRows()
            return entries

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
        self._entries: Tuple[Tuple[PreviewSession, TokenChange], ...] = tuple(
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

            def build_plan():
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

            def refresh_batch_summary(*_args):
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
            for preview, change in batch.entries:
                preview.restore_decision(change.change_id, target)
            self._record_scoped_bulk_decision_action(
                before_decisions, target, batch.change_count)
            for file_id, change_ids, states in before_decisions:
                for state in states:
                    previous = None if state == 0 else _DECISION_VALUES[state - 1]
                    self._record_decision_change(file_id, previous, target)
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
        combo: Any, label: str, values: Sequence[Tuple[str, str]], translator: Translator,
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

    def _visible_entries(self) -> Tuple[Tuple[PreviewSession, TokenChange], ...]:
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

    def _selected_change_identity(self) -> Tuple[str, str] | None:
        row = self._current_row()
        entries = self._visible_entries_cache
        if 0 <= row < len(entries):
            change = entries[row][1]
            return change.file_id, change.change_id
        return None

    def _navigate_to_related_change(self, identity: Tuple[str, str]) -> None:
        """Reveal a real related preview row without changing its decision."""

        self._clear_filters()
        file_id, change_id = identity
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
        embedded=True,
        container=None,
        parent_dialog=None,
    ) -> None:
        self._qt = qt_widgets
        self._jieba_configs = jieba_configs
        self._translator = translator
        self._jieba_probe = jieba_probe
        self._ui_preferences = dict(ui_preferences or {})
        if not embedded:
            raise ValueError("Conversion configuration must be embedded in the scope chooser")
        self._probe_error = None
        self._probe_state = "not_started"
        self._default_base = BASE_CONFIG_BY_JIEBA.get(default_config, default_config)
        self._preferred_jieba = default_config in BASE_CONFIG_BY_JIEBA
        self._direction_reselected = not self._preferred_jieba
        self._jieba_auto_checked = False
        self._updating_jieba = False
        self.accepted = False
        self.selected_config = None
        self.dialog = parent_dialog or qt_widgets.QDialog()

        layout = qt_widgets.QVBoxLayout(container or self.dialog)
        self.explanation_label = qt_widgets.QLabel(
            self._translator.text("config.explanation"))
        self.explanation_label.setWordWrap(True)
        layout.addWidget(self.explanation_label)

        self.direction_label = qt_widgets.QLabel(
            self._translator.text("config.direction"))
        self.combo = qt_widgets.QComboBox()
        self.direction_label.setBuddy(self.combo)
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
        self.jieba_status = qt_widgets.QLabel()
        self.jieba_status.setWordWrap(True)
        layout.addWidget(self.jieba_status)
        self.jieba_checkbox = qt_widgets.QCheckBox(self._translator.text("config.jieba"))
        self.jieba_checkbox.setToolTip(self._translator.text("config.jieba_tooltip"))
        layout.addWidget(self.jieba_checkbox)
        from ui.run_options import RunOptionsPanel
        self.options_panel = RunOptionsPanel(
            qt_widgets, translator, layout, initial=initial_options,
            metadata_available=metadata_available, nav_available=nav_available,
            services=services, ui_preferences=self._ui_preferences,
        )
        self.options_panel.bind(self._get_config, self._set_config, self.dialog)

        self._completion_enabled_callback = None
        self.combo.currentIndexChanged.connect(self._direction_changed)
        self.jieba_checkbox.stateChanged.connect(self._update_jieba_state)
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
        controls_visible = not (
            self._probe_state == "unavailable" and not self._preferred_jieba)
        self.jieba_checkbox.setVisible(controls_visible)
        self.jieba_status.setVisible(controls_visible)
        self.options_panel.update_enablement(self._get_config())
        callback = self._completion_enabled_callback
        if callable(callback):
            callback()

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

    def _stop_probe_timer(self):
        timer = getattr(self, "_probe_timer", None)
        if timer is not None:
            timer.stop()

    def _accept(self, *, close=True) -> None:
        from app.errors import RuleConflictError
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
        except (ValueError, RuleConflictError) as exc:
            show_error_details(
                self._qt, self.dialog, self._translator.text("config.title"),
                settings_error_message(self._translator, exc), str(exc),
            )
            return
        self._stop_probe_timer()
        self.selected_config = ConfigurationChoice(
            config, options, preference_options=preference_options)
        self.accepted = True
        if close:
            self.dialog.accept()

    def _retranslate(self) -> None:
        """Refresh visible text after the shared language selector changes."""
        self.dialog.setWindowTitle(plugin_window_title(
            self._translator, self._translator.text("main.title")))
        self.explanation_label.setText(self._translator.text("config.explanation"))
        self.direction_label.setText(self._translator.text("config.direction"))
        selected = self.combo.currentData()
        blocked = self.combo.blockSignals(True)
        try:
            for index in range(self.combo.count()):
                config = self.combo.itemData(index)
                if config:
                    self.combo.setItemText(index, self._translator.text(f"config.{config}"))
        finally:
            self.combo.blockSignals(blocked)
        selected_index = self.combo.findData(selected)
        if selected_index >= 0:
            self.combo.setCurrentIndex(selected_index)
        self.jieba_checkbox.setText(self._translator.text("config.jieba"))
        self.jieba_checkbox.setToolTip(self._translator.text("config.jieba_tooltip"))
        self.options_panel.retranslate()
        self._apply_jieba_state()

    def _continue_is_allowed(self) -> bool:
        if self._preferred_jieba and self._probe_state in {"not_started", "pending"}:
            return False
        if (self._preferred_jieba and self._probe_state == "unavailable"
                and not self._direction_reselected):
            return False
        return True

def _information_icon_label(qt_widgets: Any, parent: Any, translator: Translator) -> Any:
    label = qt_widgets.QLabel()
    set_accessible_name = getattr(label, "setAccessibleName", None)
    if callable(set_accessible_name):
        set_accessible_name(translator.text("a11y.scope.information"))
    style_type = getattr(qt_widgets, "QStyle", None)
    pixmap_type = getattr(style_type, "StandardPixmap", style_type)
    information_type = getattr(pixmap_type, "SP_MessageBoxInformation", None)
    style_getter = getattr(parent, "style", None)
    style = style_getter() if callable(style_getter) else None
    standard_icon = getattr(style, "standardIcon", None)
    if information_type is not None and callable(standard_icon):
        icon = standard_icon(information_type)
        pixmap = getattr(icon, "pixmap", None)
        set_pixmap = getattr(label, "setPixmap", None)
        if callable(pixmap) and callable(set_pixmap):
            set_pixmap(pixmap(20, 20))
            return label
    set_text = getattr(label, "setText", None)
    if callable(set_text):
        set_text("ℹ")
    return label

def _set_scope_banner_surface(banner: Any, qt_widgets: Any) -> None:
    object_name = "openccForSigilScopeNoticeBanner"
    set_object_name = getattr(banner, "setObjectName", None)
    if callable(set_object_name):
        set_object_name(object_name)
    palette_getter = getattr(banner, "palette", None)
    palette = palette_getter() if callable(palette_getter) else None
    gui = getattr(qt_widgets, "QtGui", None)
    palette_type = getattr(gui, "QPalette", None)
    role = _enum_value(palette_type, "AlternateBase")
    if role is None:
        role = _enum_value(palette_type, "Base")
    color_getter = getattr(palette, "color", None)
    if role is None or not callable(color_getter):
        return
    try:
        color = color_getter(role)
    except (TypeError, ValueError):
        return
    name_getter = getattr(color, "name", None)
    color_name = name_getter() if callable(name_getter) else None
    if not isinstance(color_name, str) or not color_name:
        return
    set_style_sheet = getattr(banner, "setStyleSheet", None)
    if callable(set_style_sheet):
        set_style_sheet(
            f"QWidget#{object_name} {{ background-color: {color_name}; }}")

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
        embedded=True,
        container=None,
        parent_dialog=None,
    ) -> None:
        self._qt = qt_widgets
        self._inventory = inventory
        self._translator = translator
        if not embedded:
            raise ValueError("Scope selection must be embedded in the combined chooser")
        self._language_changed_callback = None
        self._analysis_enabled_callback = None
        self.accepted = False
        self.selection = None
        self.language = language
        self.ignored_non_xhtml = max(0, ignored_non_xhtml)
        self.spine_ids = tuple(file_id for file_id in spine_ids if file_id)
        self.nav_id = nav_id
        self._manual_selection_ids = set(initial_ids)
        self._recovery_notices = tuple(recovery_notices)
        self._updating_items = False
        self.dialog = parent_dialog or qt_widgets.QDialog()
        layout = qt_widgets.QVBoxLayout(container or self.dialog)
        self.recovery_notice_label = None
        self.recovery_notice_banner = None
        self.recovery_notice_icon_label = None
        if self._recovery_notices:
            notice_lines = [
                _recovery_notice_text(kind, value, translator)
                for kind, value in self._recovery_notices
            ]
            self.recovery_notice_banner = qt_widgets.QWidget()
            recovery_layout = qt_widgets.QHBoxLayout(self.recovery_notice_banner)
            self.recovery_notice_icon_label = _information_icon_label(
                qt_widgets, self.recovery_notice_banner, translator)
            recovery_layout.addWidget(self.recovery_notice_icon_label)
            self.recovery_notice_label = qt_widgets.QLabel("\n".join(notice_lines))
            self.recovery_notice_label.setWordWrap(True)
            recovery_layout.addWidget(self.recovery_notice_label, 1)
            _set_scope_banner_surface(self.recovery_notice_banner, qt_widgets)
            layout.addWidget(self.recovery_notice_banner)
        self.language_label = qt_widgets.QLabel(translator.text("language.label"))
        self.language_combo = qt_widgets.QComboBox()
        self.language_label.setBuddy(self.language_combo)
        self.language_label.setAccessibleName(translator.text("a11y.scope.language"))
        for code in SUPPORTED_LANGUAGES:
            self.language_combo.addItem(self._translator.text(f"language.name.{code}"), code)
        self.language_combo.setCurrentIndex(max(0, self.language_combo.findData(language)))
        self.language_combo.currentIndexChanged.connect(self._language_changed)

        self.selected_radio = qt_widgets.QRadioButton(translator.text("scope.selected"))
        self.spine_radio = qt_widgets.QRadioButton(translator.text("scope.spine"))
        self.all_radio = qt_widgets.QRadioButton(translator.text("scope.all"))
        self.selected_radio.setChecked(True)
        radio_row = qt_widgets.QHBoxLayout()
        for radio in (self.selected_radio, self.spine_radio, self.all_radio):
            radio_row.addWidget(radio)
            radio.toggled.connect(self._refresh_enabled)
        layout.addLayout(radio_row)

        self.filter_edit = qt_widgets.QLineEdit()
        self.filter_edit.setPlaceholderText(translator.text("scope.filter"))
        self.filter_edit.setAccessibleName(translator.text("a11y.scope.filter_files"))
        self.filter_edit.textChanged.connect(self._refresh_list)
        self.filter_edit.returnPressed.connect(self._focus_first_visible_item)
        self._install_filter_enter_guard(qt_widgets)
        layout.addWidget(self.filter_edit)
        self.guide_label = qt_widgets.QLabel(translator.text("scope.selection_guide"))
        self.guide_label.setWordWrap(True)
        self.guide_label.setVisible(not bool(initial_ids))
        layout.addWidget(self.guide_label)
        self.list_widget = qt_widgets.QListWidget()
        self.list_widget.setAccessibleName(translator.text("a11y.scope.file_list"))
        elide_middle = _enum_value(qt_widgets.Qt, "ElideMiddle")
        if elide_middle is not None:
            self.list_widget.setTextElideMode(elide_middle)
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

        self.select_visible.clicked.connect(lambda: self._set_visible(True))
        self.clear_visible.clicked.connect(lambda: self._set_visible(False))

        initial = set(initial_ids)
        for item in inventory:
            label = self._scope_item_label(item)
            row = qt_widgets.QListWidgetItem(label)
            row.setToolTip(item.href)
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
        if initial_scope is Scope.SPINE:
            self.spine_radio.setChecked(True)
        elif initial_scope is Scope.ALL_XHTML:
            self.all_radio.setChecked(True)
        else:
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

    def _filter_enter_pressed(self) -> bool:
        self._focus_first_visible_item()
        return True

    def _install_filter_enter_guard(self, qt_widgets: Any) -> None:
        core = getattr(qt_widgets, "QtCore", None)
        qobject = getattr(core, "QObject", None)
        qevent = getattr(core, "QEvent", None)
        if qobject is None or qevent is None:
            return
        key_press = getattr(qevent, "KeyPress", None)
        if key_press is None:
            key_press = getattr(getattr(qevent, "Type", qevent), "KeyPress", None)
        keys = {
            _enum_value(qt_widgets.Qt, "Key_Return"),
            _enum_value(qt_widgets.Qt, "Key_Enter"),
        }
        keys.discard(None)
        if key_press is None or not keys:
            return
        owner = self

        class _Guard(qobject):
            def eventFilter(_self, _target, event):
                return (event.type() == key_press and event.key() in keys
                        and owner._filter_enter_pressed())

        self._filter_enter_guard = _Guard(self.filter_edit)
        self.filter_edit.installEventFilter(self._filter_enter_guard)

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
        self._refresh_count()
        self._update_analyze_enabled()

    def _language_changed(self) -> None:
        code = str(self.language_combo.currentData())
        self.language = code
        self._translator.set_language(code)
        self.dialog.setWindowTitle(plugin_window_title(
            self._translator, self._translator.text("main.title")))
        self.language_label.setText(self._translator.text("language.label"))
        self.language_label.setAccessibleName(self._translator.text("a11y.scope.language"))
        self.guide_label.setText(self._translator.text("scope.selection_guide"))
        for row, item in enumerate(self._inventory):
            self.list_widget.item(row).setText(self._scope_item_label(item))
        if self.recovery_notice_label is not None and self.recovery_notice_label.isVisible():
            self.recovery_notice_label.setText("\n".join(
                _recovery_notice_text(kind, value, self._translator)
                for kind, value in self._recovery_notices
            ))
            set_accessible_name = getattr(
                self.recovery_notice_icon_label, "setAccessibleName", None)
            if callable(set_accessible_name):
                set_accessible_name(self._translator.text("a11y.scope.information"))
        self.selected_radio.setText(self._translator.text("scope.selected"))
        self.spine_radio.setText(self._translator.text("scope.spine"))
        self.all_radio.setText(self._translator.text("scope.all"))
        self.filter_edit.setPlaceholderText(self._translator.text("scope.filter"))
        self.filter_edit.setAccessibleName(self._translator.text("a11y.scope.filter_files"))
        self.list_widget.setAccessibleName(self._translator.text("a11y.scope.file_list"))
        self.select_visible.setText(self._translator.text("scope.select_visible"))
        self.clear_visible.setText(self._translator.text("scope.clear_visible"))
        self._refresh_count()
        self._update_analyze_enabled()
        if callable(self._language_changed_callback):
            self._language_changed_callback()

    def _scope_item_label(self, item: TextFile) -> str:
        label = item.href
        if item.file_id == self.nav_id:
            label += " " + self._translator.text("scope.navigation_suffix")
        return label

    def _checked_ids(self) -> Tuple[str, ...]:
        checked = self._qt.Qt.Checked
        return tuple(
            self.list_widget.item(index).data(self._qt.Qt.UserRole)
            for index in range(self.list_widget.count())
            if self.list_widget.item(index).checkState() == checked
        )

    def selected_ids(self) -> Tuple[str, ...]:
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
        selected = len(self.selected_ids())
        visible = sum(not self.list_widget.item(index).isHidden()
                      for index in range(total))
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
        mode = ("spine" if self.spine_radio.isChecked() else
                "all" if self.all_radio.isChecked() else "selected")
        qt = self._qt.Qt
        checkable = getattr(qt, "ItemIsUserCheckable", 16)
        self._updating_items = True
        self.list_widget.blockSignals(True)
        try:
            available = {item.file_id for item in self._inventory}
            fixed_ids = (set(self.spine_ids) & available if mode == "spine" else
                         available if mode == "all" else set())
            for index in range(self.list_widget.count()):
                item = self.list_widget.item(index)
                file_id = item.data(qt.UserRole)
                if mode == "selected":
                    item.setFlags(item.flags() | checkable)
                    checked = file_id in self._manual_selection_ids
                else:
                    item.setFlags(item.flags() & ~checkable)
                    checked = file_id in fixed_ids
                item.setCheckState(qt.Checked if checked else qt.Unchecked)
            self.guide_label.setVisible(
                mode == "selected" and not self._manual_selection_ids)
        finally:
            self.list_widget.blockSignals(False)
            self._updating_items = False

    def _update_analyze_enabled(self) -> None:
        callback = self._analysis_enabled_callback
        if callable(callback):
            callback()

    def _selection_is_valid(self) -> bool:
        count = len(self.selected_ids())
        valid = bool(self._inventory)
        if self.selected_radio.isChecked():
            valid = count > 0
        elif self.spine_radio.isChecked():
            valid = bool(self.spine_ids)
        return valid

    def _accept(self, *, close=True) -> None:
        try:
            scope = (
                Scope.ALL_XHTML if self.all_radio.isChecked()
                else Scope.SPINE if self.spine_radio.isChecked()
                else Scope.SELECTED
            )
            ids = self.spine_ids if scope is Scope.SPINE else self.selected_ids()
            selection = resolve_target_selection(self._inventory, scope, ids)
            if selection.empty:
                raise ScopeSelectionError(self._translator.text("scope.none"))
        except ScopeSelectionError:
            self._qt.QMessageBox.warning(
                self.dialog,
                plugin_window_title(
                    self._translator, self._translator.text("scope.title")),
                self._translator.text("scope.none"),
            )
            return
        self.scope = scope
        self.selection = selection
        self.accepted = True
        if close:
            self.dialog.accept()
