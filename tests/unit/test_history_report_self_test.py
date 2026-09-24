from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.self_test import run_self_test
from app.profiles import Profile, ProfileStore
from logging_ext.history import HistoryError, HistoryStore
from logging_ext.report import ReportError, export_json, export_markdown
from logging_ext.retention import cleanup
from tests.support.fake_qt import make_with_table
from ui import history_window
from ui.history_window import (
    _configure_history_table,
    _render_table,
    cleanup_with_confirmation,
    history_rows,
)
from ui.i18n import Translator, configuration_label


SESSION_ID = "123e4567-e89b-12d3-a456-426614174000"
SUMMARY = {
    "session_id": SESSION_ID,
    "status": "success",
    "state": "completed",
    "book_name": "Book.epub",
    "profile_id": "conservative",
    "config": "s2twp",
    "files_scanned": 1,
    "files_changed": 1,
    "changes": 2,
    "source": "should not be persisted",
}
MANIFEST = {
    "session_id": SESSION_ID,
    "files": [
        {
            "id": "text/chapter.xhtml",
            "href": "Text/chapter.xhtml",
            "before_sha256": "a" * 64,
            "after_sha256": "b" * 64,
            "change_count": 2,
        }
    ],
}
PROVENANCE = {"opencc_version": "1.4.2", "python_abi": "cp314"}


def test_history_persists_metadata_hashes_and_rejects_text(tmp_path: Path):
    store = HistoryStore(tmp_path / "history")
    record = store.record_session(SUMMARY, MANIFEST, PROVENANCE)
    assert record["summary"]["book_name"] == "Book.epub"
    assert "source" not in record["summary"]
    assert record["commit_manifest"]["files"][0]["before_sha256"] == "a" * 64
    assert json.loads((tmp_path / "history" / "index.json").read_text(encoding="utf-8"))["schema_version"] == 1


def test_history_corruption_is_visible_and_not_reset(tmp_path: Path):
    root = tmp_path / "history"
    root.mkdir()
    (root / "index.json").write_text("{", encoding="utf-8")
    with pytest.raises(HistoryError):
        HistoryStore(root).load()


def test_report_metadata_default_and_explicit_full_diff(tmp_path: Path):
    metadata = tmp_path / "metadata.json"
    export_json(metadata, SUMMARY, MANIFEST, PROVENANCE)
    payload = json.loads(metadata.read_text(encoding="utf-8"))
    assert "full_diff" not in payload
    with pytest.raises(ReportError):
        export_json(
            tmp_path / "missing.json", SUMMARY, MANIFEST, PROVENANCE, include_full_diff=True
        )
    full = [{"href": "Text/chapter.xhtml", "source": "软件", "target": "軟體"}]
    markdown = tmp_path / "report.md"
    export_markdown(
        markdown,
        SUMMARY,
        MANIFEST,
        PROVENANCE,
        full_diff=full,
        include_full_diff=True,
    )
    assert "软件 → 軟體" in markdown.read_text(encoding="utf-8")


def test_retention_is_explicit_and_scoped_to_session_files(tmp_path: Path):
    history_root = tmp_path / "history"
    logs_root = tmp_path / "logs"
    store = HistoryStore(history_root)
    old_id = "123e4567-e89b-12d3-a456-426614174001"
    old_summary = {**SUMMARY, "session_id": old_id}
    old_manifest = {**MANIFEST, "session_id": old_id}
    old_time = datetime.now(timezone.utc) - timedelta(days=60)
    store.record_session(old_summary, old_manifest, PROVENANCE, recorded_at=old_time)
    month = logs_root / old_time.strftime("%Y-%m")
    month.mkdir(parents=True)
    (month / f"{old_id}.jsonl").write_text("{}\n", encoding="utf-8")
    (month / "keep-me.txt").write_text("keep", encoding="utf-8")
    result = cleanup(history_root, logs_root, now=datetime.now(timezone.utc))
    assert old_id in result.removed_sessions
    assert not (month / f"{old_id}.jsonl").exists()
    assert (month / "keep-me.txt").exists()
    assert HistoryStore(history_root).load() == []


def test_retention_never_follows_log_directory_symlinks(tmp_path: Path):
    root = tmp_path / "history"
    old = datetime.now(timezone.utc) - timedelta(days=60)
    HistoryStore(root).record_session(SUMMARY, MANIFEST, PROVENANCE, recorded_at=old)
    outside = tmp_path / "outside"
    outside.mkdir()
    retained = outside / f"{SESSION_ID}.jsonl"
    retained.write_text("outside plugin log tree")
    logs = tmp_path / "logs"
    logs.mkdir()
    try:
        (logs / old.strftime("%Y-%m")).symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("host does not allow directory symlinks")
    result = cleanup(root, logs)
    assert result.removed_log_files == ()
    assert retained.read_text() == "outside plugin log tree"


class _BackendResult:
    passed = True
    checks = {"s2t_smoke": True}
    error = None


class _Backend:
    def self_test(self, *, include_optional: bool):
        return _BackendResult()

    def close(self):
        return None


def test_self_test_uses_injected_backend_and_writes_no_book(tmp_path: Path):
    calls = []

    def factory(config: str):
        calls.append(config)
        return _Backend()

    report = run_self_test(backend_factory=factory, data_dir=tmp_path / "plugin-data")
    assert report.passed
    assert report.checks["backend_standard"] and report.checks["backend_full"]
    assert report.checks["storage"] and report.checks["logging"]
    assert calls == ["s2t", "s2t"]
    assert not list((tmp_path / "plugin-data").rglob(".self-test-*"))


def test_history_rows_expose_metadata_only():
    translator = Translator("en")

    rows = history_rows(
        [
            {
                "recorded_at": "2026-01-01T00:00:00+00:00",
                "summary": {
                    "book_label": "Book.epub",
                    "config": "s2t",
                    "changes": 3,
                    "status": "success",
                },
            }
        ],
        translator=translator,
    )
    expected_date = datetime.fromisoformat("2026-01-01T00:00:00+00:00").astimezone().strftime(
        "%Y-%m-%d %H:%M")
    assert rows == [(
        expected_date, "Book.epub", "—", configuration_label(translator, "s2t"),
        "0", "3", translator.text("history.status.success"),
    )]


def test_history_old_records_show_empty_book_label():
    rows = history_rows([{"recorded_at": "2026-01-01T00:00:00+00:00", "summary": {}}])
    assert rows[0][1] == "—"


def test_history_rows_show_profile_name_and_localized_direction_and_sort_counts_numerically(
    tmp_path,
):
    profiles = ProfileStore(tmp_path / "user-data")
    profiles.save(Profile(id="profile-123456", name="My reading profile"))
    translator = Translator("zh-Hans")
    record = {
        "recorded_at": "2026-01-01T00:00:00+00:00",
        "session_id": SESSION_ID,
        "summary": {
            "profile_id": "profile-123456",
            "config": "s2t",
            "files_changed": 12,
            "changes": 5,
        },
    }

    rows = history_rows([record], translator=translator, profile_store=profiles)
    assert rows[0][2] == "My reading profile"
    assert rows[0][3] == configuration_label(translator, "s2t")

    qt = make_with_table()
    table = qt.QTableWidget(0, 7)
    _render_table(table, [record], qt, translator, profile_store=profiles)
    assert isinstance(table.item(0, 4).data(qt.Qt.DisplayRole), int)
    assert isinstance(table.item(0, 5).data(qt.Qt.DisplayRole), int)


def test_missing_history_profile_uses_short_id_fallback():
    rows = history_rows(
        [{"recorded_at": "2026-01-01T00:00:00+00:00", "summary": {"profile_id": "profile-123456"}}]
    )
    assert rows[0][2] == "profile-"


def test_history_dialog_uses_the_adjacent_profile_store(monkeypatch, tmp_path):
    user_data = tmp_path / "user-data"
    ProfileStore(user_data).save(Profile(id="profile-123456", name="My profile"))
    history_root = user_data / "history"
    HistoryStore(history_root).record_session(
        {**SUMMARY, "profile_id": "profile-123456", "config": "s2t"},
        MANIFEST,
        PROVENANCE,
    )
    monkeypatch.setattr(history_window, "ensure_application", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(history_window, "exec_dialog", lambda *_args: None)

    qt = make_with_table()
    dialog = history_window.show_history(
        history_root, language="zh-Hans", qt_widgets=qt
    )

    assert dialog.history_table.item(0, 2).text() == "My profile"
    assert dialog.history_table.item(0, 3).text() == configuration_label(
        Translator("zh-Hans"), "s2t"
    )


def test_cleanup_confirmation_runs_dry_run_before_delete_and_respects_cancel(tmp_path):
    history_root = tmp_path / "history"
    logs_root = tmp_path / "logs"
    store = HistoryStore(history_root)
    old_id = "123e4567-e89b-12d3-a456-426614174002"
    old_time = datetime.now(timezone.utc) - timedelta(days=60)
    store.record_session({**SUMMARY, "session_id": old_id},
                         {**MANIFEST, "session_id": old_id}, PROVENANCE,
                         recorded_at=old_time)
    month = logs_root / old_time.strftime("%Y-%m")
    month.mkdir(parents=True)
    log = month / f"{old_id}.jsonl"
    log.write_text("{}\n", encoding="utf-8")
    prompts = []

    completed, _preview = cleanup_with_confirmation(
        history_root, logs_root,
        lambda result: prompts.append((len(result.removed_sessions),
                                       len(result.removed_log_files))) or False,
        now=datetime.now(timezone.utc),
    )
    assert not completed
    assert prompts == [(1, 1)]
    assert len(HistoryStore(history_root).load()) == 1
    assert log.exists()

    completed, result = cleanup_with_confirmation(
        history_root, logs_root, lambda _preview: True, now=datetime.now(timezone.utc))
    assert completed
    assert len(result.removed_sessions) == 1
    assert HistoryStore(history_root).load() == []
    assert not log.exists()


def test_history_table_is_not_editable_and_selects_whole_rows():
    class View:
        NoEditTriggers = 7
        SelectRows = 9

    class Table:
        def setEditTriggers(self, value):
            self.edit_triggers = value

        def setSelectionBehavior(self, value):
            self.selection = value

    table = Table()
    _configure_history_table(table, SimpleNamespace(QAbstractItemView=View))
    assert table.edit_triggers == View.NoEditTriggers
    assert table.selection == View.SelectRows


def test_history_dialog_button_defaults_and_empty_cleanup_state(monkeypatch, tmp_path):
    qt = make_with_table()
    monkeypatch.setattr(history_window, "ensure_application", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(history_window, "exec_dialog", lambda *_args: None)

    dialog = history_window.show_history(tmp_path / "history", qt_widgets=qt)

    assert not dialog.cleanup_button.isEnabled()
    assert dialog.history_buttons[1].isDefault()
    assert all(button.autoDefault() is False for button in dialog.history_buttons)
