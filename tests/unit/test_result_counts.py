from pathlib import Path

import pytest

from app.controller import Controller
from ui import preview_window
from ui.i18n import Translator


@pytest.mark.parametrize(
    ("files_scanned", "files_changed", "files_without_changes"),
    (
        (2, 1, 1),  # one write, one unchanged
        (2, 0, 0),  # all proposed changes skipped
        (2, 1, 0),  # one write, one skipped-only file
        (2, 0, 2),  # all files unchanged
    ),
)
def test_controller_summary_keeps_unwritten_total_and_unchanged_subset(
    tmp_path: Path,
    files_scanned: int,
    files_changed: int,
    files_without_changes: int,
):
    summary = Controller(object(), data_dir=tmp_path / "plugin-data")._summary(
        status="success",
        files_scanned=files_scanned,
        files_changed=files_changed,
        files_without_changes=files_without_changes,
        changes=0,
    )

    assert summary["files_not_written"] == files_scanned - files_changed
    assert summary["files_without_changes"] <= summary["files_not_written"]


class _MessageBox:
    messages = []

    @classmethod
    def information(cls, _parent, _title, message):
        cls.messages.append(message)

    @classmethod
    def warning(cls, _parent, _title, message):
        cls.messages.append(message)


@pytest.mark.parametrize(
    (
        "language",
        "files_scanned",
        "files_changed",
        "accepted_changes",
        "skipped_changes",
        "files_not_written",
        "files_without_changes",
        "expected_unwritten",
    ),
    (
        ("en", 1, 1, 1, 0, 0, 0, "Files not written: 0 (no proposed changes: 0)"),
        ("en", 2, 1, 1, 0, 1, 1, "Files not written: 1 (no proposed changes: 1)"),
        ("en", 3, 1, 1, 2, 2, 2, "Files not written: 2 (no proposed changes: 2)"),
        ("zh-Hans", 1, 1, 1, 0, 0, 0, "未写回：0 个文件（其中没有建议变更：0 个）"),
        ("zh-Hans", 2, 1, 1, 0, 1, 1, "未写回：1 个文件（其中没有建议变更：1 个）"),
        ("zh-Hans", 3, 1, 1, 2, 2, 2, "未写回：2 个文件（其中没有建议变更：2 个）"),
        ("zh-Hant", 1, 1, 1, 0, 0, 0, "未寫回：0 個檔案（其中沒有建議變更：0 個）"),
        ("zh-Hant", 2, 1, 1, 0, 1, 1, "未寫回：1 個檔案（其中沒有建議變更：1 個）"),
        ("zh-Hant", 3, 1, 1, 2, 2, 2, "未寫回：2 個檔案（其中沒有建議變更：2 個）"),
    ),
)
def test_result_done_states_unwritten_files_include_unchanged_subset(
    monkeypatch,
    language: str,
    files_scanned: int,
    files_changed: int,
    accepted_changes: int,
    skipped_changes: int,
    files_not_written: int,
    files_without_changes: int,
    expected_unwritten: str,
):
    _MessageBox.messages = []
    fake_qt = type("FakeQt", (), {"QMessageBox": _MessageBox})
    monkeypatch.setattr(preview_window, "_load_qt_widgets", lambda: fake_qt)
    monkeypatch.setattr(preview_window, "_ensure_application", lambda _qt: None)
    preview_window.set_ui_language(language)

    preview_window.show_result(
        status="success",
        files_scanned=files_scanned,
        files_changed=files_changed,
        accepted_changes=accepted_changes,
        skipped_changes=skipped_changes,
        files_not_written=files_not_written,
        files_without_changes=files_without_changes,
    )

    assert len(_MessageBox.messages) == 1
    lines = _MessageBox.messages[0].splitlines()
    assert str(files_scanned) in lines[2]
    assert str(files_changed) in lines[3]
    assert str(accepted_changes) in lines[3]
    assert str(skipped_changes) in lines[3]
    assert lines[4] == expected_unwritten
    preview_window.set_ui_language("en")


def test_noop_result_offers_scope_return_and_lists_invalid_sources(monkeypatch):
    class Button:
        def __init__(self, label, role):
            self.label = label
            self.role = role

    class MessageBox:
        RejectRole = "reject"
        AcceptRole = "accept"
        response = "back"
        instances = []

        @classmethod
        def information(cls, *_args):
            raise AssertionError("interactive result box should be used")

        @classmethod
        def warning(cls, *_args):
            raise AssertionError("interactive result box should be used")

        def __init__(self):
            self.buttons = []
            self.text = ""
            self.default_button = None
            self.instances.append(self)

        def setWindowTitle(self, _title):
            pass

        def setText(self, text):
            self.text = text

        def addButton(self, label, role):
            button = Button(label, role)
            self.buttons.append(button)
            return button

        def setDefaultButton(self, button):
            self.default_button = button

        def exec(self):
            pass

        def clickedButton(self):
            return self.buttons[0] if self.response == "back" else self.buttons[1]

    fake_qt = type("FakeQt", (), {"QMessageBox": MessageBox})
    monkeypatch.setattr(preview_window, "_load_qt_widgets", lambda: fake_qt)
    monkeypatch.setattr(preview_window, "_ensure_application", lambda _qt: None)
    preview_window.set_ui_language("zh-Hans")

    values = dict(
        status="success",
        files_scanned=1,
        files_changed=0,
        accepted_changes=0,
        skipped_changes=0,
        return_to_scope=True,
        diagnostics=(("Text/bad.xhtml", "SOURCE_INVALID_XHTML", "line 1, column 2"),),
    )
    assert preview_window.show_result(**values) == "back_to_scope"
    back_box = MessageBox.instances[-1]
    assert "没有需要转换的内容" in back_box.text
    assert "以下源文件 XHTML 不合法，已跳过：" in back_box.text
    invalid_source = Translator("zh-Hans").text(
        "diagnostic.source_invalid_xhtml", count=1)
    assert f"Text/bad.xhtml: {invalid_source}" in back_box.text
    assert "line 1, column 2" not in back_box.text
    assert [button.label for button in back_box.buttons] == ["返回文件选择", "关闭"]
    assert back_box.default_button is back_box.buttons[1]

    MessageBox.response = "close"
    assert preview_window.show_result(**values) == "close"
    close_box = MessageBox.instances[-1]
    assert close_box.default_button is close_box.buttons[1]
    preview_window.set_ui_language("en")


@pytest.mark.parametrize("language", ("en", "zh-Hans", "zh-Hant"))
@pytest.mark.parametrize(
    ("status", "accepted", "skipped", "status_key", "reminder"),
    (
        ("success", 1, 0, "result.status.success", True),
        ("partial_failure", 2, 1, "result.status.partial", False),
        ("cancelled", 0, 0, "result.status.cancelled", False),
        ("success", 0, 0, "result.status.noop", False),
        ("success", 0, 2, "result.status.skipped", False),
    ),
)
def test_result_status_and_count_rows_are_localized_line_by_line(
    monkeypatch, language, status, accepted, skipped, status_key, reminder,
):
    _MessageBox.messages = []
    fake_qt = type("FakeQt", (), {"QMessageBox": _MessageBox})
    monkeypatch.setattr(preview_window, "_load_qt_widgets", lambda: fake_qt)
    monkeypatch.setattr(preview_window, "_ensure_application", lambda _qt: None)
    preview_window.set_ui_language(language)
    translator = Translator(language)

    preview_window.show_result(
        status=status,
        files_scanned=4,
        files_changed=1,
        accepted_changes=accepted,
        skipped_changes=skipped,
        files_not_written=3,
        files_without_changes=1,
        failed_file="Text/ch.xhtml",
    )

    assert len(_MessageBox.messages) == 1
    lines = _MessageBox.messages[0].splitlines()
    expected_status = translator.text(
        status_key, file="Text/ch.xhtml") if status_key.endswith("partial") else translator.text(status_key)
    assert lines[0] == expected_status
    assert lines[2] == translator.text("result.row.scanned", count=4)
    assert lines[3] == translator.text(
        "result.row.written", files=1, accepted=accepted, skipped=skipped)
    assert lines[4] == translator.text(
        "result.row.unwritten", files=3, unchanged=1)
    if reminder:
        assert lines[6] == translator.text("result.save_reminder")
    else:
        assert translator.text("result.save_reminder") not in lines
    preview_window.set_ui_language("en")


def test_success_result_opens_this_sessions_markdown_report(monkeypatch):
    class Button:
        def __init__(self, label):
            self.label = label

    class MessageBox:
        ActionRole = 1
        AcceptRole = 2
        clicked_index = 0

        @classmethod
        def information(cls, *_args):
            raise AssertionError("interactive result box should be used")

        @classmethod
        def warning(cls, *_args):
            raise AssertionError("interactive result box should be used")

        def __init__(self):
            self.buttons = []

        def setWindowTitle(self, _title):
            pass

        def setText(self, text):
            self.text = text

        def addButton(self, label, _role):
            button = Button(label)
            self.buttons.append(button)
            return button

        def setDefaultButton(self, button):
            self.default = button

        def exec(self):
            pass

        def clickedButton(self):
            return self.buttons[self.clicked_index]

    fake_qt = type("FakeQt", (), {"QMessageBox": MessageBox})
    monkeypatch.setattr(preview_window, "_load_qt_widgets", lambda: fake_qt)
    monkeypatch.setattr(preview_window, "_ensure_application", lambda _qt: None)
    opened = []
    monkeypatch.setattr(
        preview_window, "_show_report_text", lambda _qt, text: opened.append(text))
    preview_window.set_ui_language("zh-Hans")

    assert preview_window.show_result(
        status="success", files_scanned=1, files_changed=1,
        accepted_changes=1, skipped_changes=0, report_text="# session report",
    ) == "close"
    assert opened == ["# session report"]
    preview_window.set_ui_language("en")
