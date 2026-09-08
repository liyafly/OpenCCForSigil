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
