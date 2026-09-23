import pytest

from core.workflow import WorkflowCancelled, _report_progress
from ui import preview_window


class _Signal:
    def __init__(self) -> None:
        self.callback = None

    def connect(self, callback):
        self.callback = callback

    def emit(self) -> None:
        if self.callback is not None:
            self.callback()


class _FakeApplication:
    @staticmethod
    def processEvents() -> None:
        return None


class _FakeProgressDialog:
    def __init__(self, _label, _cancel, _minimum, maximum, parent) -> None:
        self.parent = parent
        self.canceled = _Signal()
        self.values = []
        self.maximums = []
        self.labels = []
        self.cancel_buttons = []
        self.show_calls = 0
        self.modality = None
        self.close_calls = 0
        self.window_flags = []
        self.event_filters = []

    def setWindowTitle(self, _title) -> None:
        return None

    def setWindowModality(self, modality) -> None:
        self.modality = modality

    def setMinimumDuration(self, _value) -> None:
        return None

    def setAutoClose(self, _value) -> None:
        return None

    def setAutoReset(self, _value) -> None:
        return None

    def setMaximum(self, value) -> None:
        self.maximums.append(value)

    def setValue(self, value) -> None:
        self.values.append(value)

    def setLabelText(self, value) -> None:
        self.labels.append(value)

    def setCancelButton(self, button) -> None:
        self.cancel_buttons.append(button)

    def setWindowFlag(self, flag, enabled) -> None:
        self.window_flags.append((flag, enabled))

    def installEventFilter(self, event_filter) -> None:
        self.event_filters.append(event_filter)

    def show(self) -> None:
        self.show_calls += 1

    def close(self) -> None:
        self.close_calls += 1


class _FakeQt:
    QApplication = _FakeApplication
    QProgressDialog = _FakeProgressDialog

    class Qt:
        ApplicationModal = "application-modal"
        WindowModal = "window-modal"
        WindowCloseButtonHint = "close-button"
        Key_Escape = "escape"

    class QtCore:
        class QObject:
            def __init__(self, _parent=None):
                pass

        class QEvent:
            Close = "close"
            KeyPress = "key-press"


class _FakeEvent:
    def __init__(self, kind, key=None):
        self._kind = kind
        self._key = key

    def type(self):
        return self._kind

    def key(self):
        return self._key


def test_progress_reporter_resets_each_phase_and_clamps_repeated_updates():
    preview_window.set_ui_language("en")
    reporter = preview_window.ProgressReporter(_FakeQt, 2)

    reporter.update("analyzing", 1, 2, "Text/a.xhtml")
    reporter.update("analyzing", 2, 2, "Text/b.xhtml")
    reporter.update("analyzing", 1, 2, "Text/a.xhtml")
    reporter.update("planning", 0, 1, "Text/a.xhtml")
    reporter.update("planning", 1, 1, "Text/a.xhtml")

    assert reporter.dialog.values == [0, 1, 2, 2, 0, 0, 1]
    assert reporter.dialog.maximums == [2, 1]
    assert reporter.dialog.labels[-1] == "Planning: 1/1 — Text/a.xhtml"


def test_progress_reporter_scopes_modality_to_parent_and_closes_once():
    parent = object()
    reporter = preview_window.ProgressReporter(_FakeQt, 1, parent)

    assert reporter.dialog.parent is parent
    assert reporter.dialog.modality == "window-modal"

    reporter.dialog.canceled.emit()
    assert reporter.cancelled()
    reporter.close()
    reporter.close()
    assert reporter.dialog.close_calls == 1


def test_unparented_progress_reporter_is_modal_only_inside_plugin_application():
    reporter = preview_window.ProgressReporter(_FakeQt, 0)

    assert reporter.dialog.parent is None
    assert reporter.dialog.modality == "application-modal"
    assert reporter.dialog.labels[0] == "Analyzing: 0/0 — …"


def test_cancelling_keeps_window_visible_and_preserves_cancelling_label():
    preview_window.set_ui_language("en")
    reporter = preview_window.ProgressReporter(_FakeQt, 2)

    reporter.set_cancelling()
    reporter.update("planning", 1, 2, "Text/a.xhtml")

    assert reporter.dialog.labels[-1] == "Cancelling… stopping after the current file"
    assert reporter.dialog.cancel_buttons[-1] is None
    assert reporter.dialog.show_calls >= 2


def test_non_cancellable_progress_ignores_cancel_close_and_escape():
    reporter = preview_window.ProgressReporter(_FakeQt, 2)

    reporter.disable_cancel()
    reporter.dialog.canceled.emit()

    assert reporter.cancelled() is False
    assert reporter.dialog.cancel_buttons[-1] is None
    assert reporter.dialog.window_flags == [("close-button", False)]
    assert reporter.dialog.show_calls >= 2
    event_filter = reporter.dialog.event_filters[0]
    assert event_filter.eventFilter(reporter.dialog, _FakeEvent("close")) is True
    assert event_filter.eventFilter(
        reporter.dialog, _FakeEvent("key-press", "escape")) is True
    assert event_filter.eventFilter(
        reporter.dialog, _FakeEvent("key-press", "other")) is False
    reporter.close()
    assert event_filter.eventFilter(reporter.dialog, _FakeEvent("close")) is False


def test_analysis_cancel_restores_the_window_with_cancelling_message():
    preview_window.set_ui_language("en")
    reporter = preview_window.ProgressReporter(_FakeQt, 2)
    reporter.dialog.canceled.emit()

    with pytest.raises(WorkflowCancelled):
        _report_progress(
            reporter.update,
            reporter.cancelled,
            phase="planning",
            index=1,
            total=2,
            href="Text/a.xhtml",
            cancel_message="analysis cancelled",
        )

    assert reporter.dialog.labels[-1] == "Cancelling… stopping after the current file"
    assert reporter.dialog.show_calls >= 2
