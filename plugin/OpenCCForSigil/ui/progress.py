"""Progress dialog driven by workflow file boundaries."""

from __future__ import annotations

from typing import Any

from ui.qt import enum_value as _enum_value
from ui.i18n import (
    Translator,
    plugin_window_title,
)
from ui.window_state import restore_window_size, save_window_size


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
