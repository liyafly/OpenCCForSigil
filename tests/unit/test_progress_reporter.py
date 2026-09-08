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
        self.modality = None
        self.close_calls = 0

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

    def setCancelButton(self, _button) -> None:
        return None

    def show(self) -> None:
        return None

    def close(self) -> None:
        self.close_calls += 1


class _FakeQt:
    QApplication = _FakeApplication
    QProgressDialog = _FakeProgressDialog

    class Qt:
        ApplicationModal = "application-modal"
        WindowModal = "window-modal"


def test_progress_reporter_resets_each_phase_and_clamps_repeated_updates():
    preview_window.set_ui_language("en")
    reporter = preview_window.ProgressReporter(_FakeQt, 2)

    reporter.update("analyzing", 2, 2, "Text/b.xhtml")
    reporter.update("analyzing", 1, 2, "Text/a.xhtml")
    reporter.update("planning", 1, 1, "Text/a.xhtml")

    assert reporter.dialog.values == [0, 2, 2, 0, 1]
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
