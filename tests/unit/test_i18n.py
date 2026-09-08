from ui.i18n import Translator, choose_language, load_catalogs, normalize_language
from ui import preview_window


def test_supported_catalogs_have_same_keys_and_render_placeholders():
    catalogs = load_catalogs()
    assert set(catalogs) == {"zh-Hans", "en", "zh-Hant"}
    expected = set(catalogs["en"])
    assert all(set(catalog) == expected for catalog in catalogs.values())
    for language in catalogs:
        text = Translator(language).text("scope.selected_count", selected=2, total=8)
        assert "2" in text and "8" in text
        detail = Translator(language).text("preview.change")
        assert detail and detail != "preview.change"
        progress = Translator(language).text("progress.status", phase=Translator(language).text("progress.phase.analyzing"), index=1, total=2, file="a.xhtml")
        assert "a.xhtml" in progress


def test_locale_mapping_and_preference_precedence():
    assert normalize_language("zh_TW") == "zh-Hant"
    assert normalize_language("zh-CN") == "zh-Hans"
    assert choose_language("zh-Hant", "en", "en-US") == "zh-Hant"
    assert choose_language(None, "zh-TW", "en-US") == "zh-Hant"
    assert choose_language(None, None, "de-DE") == "en"


def test_dialogs_share_one_qapplication_instance():
    class FakeApplication:
        current = None
        created = 0

        @classmethod
        def instance(cls):
            return cls.current

        def __init__(self, _args):
            type(self).created += 1
            type(self).current = self

    class FakeQt:
        QApplication = FakeApplication

    first = preview_window._ensure_application(FakeQt)
    second = preview_window._ensure_application(FakeQt)
    assert first is second
    assert preview_window._application is first
    assert FakeApplication.created == 1


def test_progress_reporter_paints_initial_state_immediately():
    events = []

    class Signal:
        def connect(self, callback):
            self.callback = callback

    class FakeApplication:
        @staticmethod
        def processEvents():
            events.append("process-events")

    class FakeProgressDialog:
        def __init__(self, *_args):
            self.canceled = Signal()
            self.minimum_duration = None
            self.value = None
            self.maximum = None
            self.label = None

        def setWindowTitle(self, _title):
            pass

        def setMinimumDuration(self, value):
            self.minimum_duration = value

        def setAutoClose(self, _value):
            pass

        def setAutoReset(self, _value):
            pass

        def setMaximum(self, value):
            self.maximum = value

        def setValue(self, value):
            self.value = value

        def setLabelText(self, value):
            self.label = value

        def show(self):
            events.append("show")

        def close(self):
            pass

    class FakeQt:
        QApplication = FakeApplication
        QProgressDialog = FakeProgressDialog

    reporter = preview_window.ProgressReporter(FakeQt, 3)

    assert reporter.dialog.minimum_duration == 0
    assert reporter.dialog.maximum == 3
    assert reporter.dialog.value == 0
    assert "0/3" in reporter.dialog.label
    assert events == ["show", "process-events"]


def test_result_dialog_explains_files_without_a_write(monkeypatch):
    messages = []

    class MessageBox:
        @staticmethod
        def information(_parent, _title, message):
            messages.append(message)

        @staticmethod
        def warning(_parent, _title, message):
            messages.append(message)

    class FakeQt:
        QMessageBox = MessageBox

    monkeypatch.setattr(preview_window, "_load_qt_widgets", lambda: FakeQt)
    monkeypatch.setattr(preview_window, "_ensure_application", lambda _qt: None)
    preview_window.set_ui_language("zh-Hans")

    preview_window.show_result(
        status="success",
        files_scanned=38,
        files_changed=37,
        accepted_changes=37,
        skipped_changes=0,
        files_without_changes=1,
    )

    assert messages == [
        "已分析 38 个文件，实际写回 37 个文件；应用 37 项变更，跳过 0 项变更；1 个文件未写回，其中 1 个文件没有建议变更。"
    ]
    preview_window.set_ui_language("en")
