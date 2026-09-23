from pathlib import Path

import pytest

from app.controller import Controller
from ui import preview_window


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
        "expected",
    ),
    (
        ("en", 1, 1, 1, 0, 0, 0, "0 files were not written, including 0 files with no proposed changes."),
        ("en", 2, 1, 1, 0, 1, 1, "1 file was not written, including 1 file with no proposed changes."),
        ("en", 3, 1, 1, 2, 2, 2, "2 files were not written, including 2 files with no proposed changes."),
        ("zh-Hans", 1, 1, 1, 0, 0, 0, "0 个文件未写回，其中 0 个文件没有建议变更。"),
        ("zh-Hans", 2, 1, 1, 0, 1, 1, "1 个文件未写回，其中 1 个文件没有建议变更。"),
        ("zh-Hans", 3, 1, 1, 2, 2, 2, "2 个文件未写回，其中 2 个文件没有建议变更。"),
        ("zh-Hant", 1, 1, 1, 0, 0, 0, "0 個檔案未寫回，其中 0 個檔案沒有建議變更。"),
        ("zh-Hant", 2, 1, 1, 0, 1, 1, "1 個檔案未寫回，其中 1 個檔案沒有建議變更。"),
        ("zh-Hant", 3, 1, 1, 2, 2, 2, "2 個檔案未寫回，其中 2 個檔案沒有建議變更。"),
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
    expected: str,
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
    assert expected in _MessageBox.messages[0]
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
    assert "Text/bad.xhtml: SOURCE_INVALID_XHTML — line 1, column 2" in back_box.text
    assert [button.label for button in back_box.buttons] == ["返回文件选择", "关闭"]
    assert back_box.default_button is back_box.buttons[1]

    MessageBox.response = "close"
    assert preview_window.show_result(**values) == "close"
    close_box = MessageBox.instances[-1]
    assert close_box.default_button is close_box.buttons[1]
    preview_window.set_ui_language("en")
