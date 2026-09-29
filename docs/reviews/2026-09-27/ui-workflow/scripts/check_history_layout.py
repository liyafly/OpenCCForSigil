"""Real Qt acceptance probe for metadata-only history filtering and actions."""

import argparse
import json
import os
import platform
from pathlib import Path
import re
import subprocess
import tempfile
import uuid
from datetime import datetime, timedelta, timezone

import PySide6

from logging_ext.history import HistoryStore
from ui import history_window
from ui.i18n import Translator
from ui.qt import ensure_application, load_qt


def _records(count=1000):
    values = []
    for index in range(count):
        session_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ux08-{index}"))
        config = ("s2t", "s2tw", "t2s", "s2t")[index % 4]
        status = ("success", "failed", "unknown_state")[index % 3]
        values.append({
            "schema_version": 1,
            "session_id": session_id,
            "recorded_at": f"2026-09-{(index % 28) + 1:02d}T{index % 24:02d}:00:00+00:00",
            "summary": {
                "session_id": session_id,
                "status": status,
                "state": "completed",
                "book_label": "中文 Book 7" if index % 17 == 7 else f"Book {index % 17}",
                "profile_id": f"profile-{index % 5}",
                "config": config,
                "files_scanned": 2,
                "files_changed": 1,
                "changes": index % 4,
            },
            "commit_manifest": {"schema_version": 1, "session_id": session_id, "files": []},
            "provenance": {"opencc_version": "1", "python_abi": "test"},
        })
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=640)
    parser.add_argument("--language", choices=("en", "zh-Hans", "zh-Hant"), default="en")
    options = parser.parse_args()
    options.output.mkdir(parents=True, exist_ok=True)
    app = ensure_application(load_qt(), language=options.language)
    qt = load_qt()
    translator = Translator(options.language)
    checks = {}
    with tempfile.TemporaryDirectory(prefix="opencc-history-") as temporary:
        root = Path(temporary) / "history"
        records = _records()
        HistoryStore(root).replace_sessions(records)
        opened, exported = [], []
        dialog = history_window.show_history(
            root, language=options.language, on_inspect=opened.append,
            on_export=lambda record, _full, _path: exported.append(record), qt_widgets=qt)
        dialog.resize(options.width, options.height)
        app.processEvents()
        checks["thousand_metadata_rows_loaded"] = dialog.history_table.rowCount() == 1000
        checks["actions_disabled_without_selection"] = (
            not dialog.history_buttons[1].isEnabled() and not dialog.history_buttons[2].isEnabled())

        # AND intersection, including a localized user-facing metadata search.
        dialog.history_search.setText("bOoK 7")
        dialog.history_direction_filter.setCurrentIndex(
            next(i for i in range(dialog.history_direction_filter.count())
                 if dialog.history_direction_filter.itemData(i) == "s2tw"))
        app.processEvents()
        expected = [record for index, record in enumerate(records)
                    if index % 17 == 7 and index % 4 == 1]
        checks["anded_filters_match_exact_metadata"] = (
            dialog.history_table.rowCount() == len(expected) and len(expected) > 0)

        # Search by a stable session ID yields one result. Sorting afterward must
        # not detach the UserRole session identity from the visible row.
        target = expected[0]
        dialog.history_direction_filter.setCurrentIndex(0)
        dialog.history_search.setText(target["session_id"])
        app.processEvents()
        table = dialog.history_table
        checks["session_id_search_is_exact"] = table.rowCount() == 1
        table.sortItems(1, qt.Qt.SortOrder.DescendingOrder)
        app.processEvents()
        role = qt.Qt.ItemDataRole.UserRole
        shown_id = table.item(0, 0).data(role)
        table.selectRow(0)
        dialog.history_buttons[1].click()
        dialog.history_buttons[2].click()
        checks["sorted_row_actions_keep_session_id"] = (
            shown_id == target["session_id"] and opened[-1]["session_id"] == shown_id
            and exported[-1]["session_id"] == shown_id)

        dialog.history_search.setText("no such metadata")
        app.processEvents()
        checks["empty_search_clears_selection_and_disables_actions"] = (
            table.rowCount() == 0 and not dialog.history_buttons[1].isEnabled()
            and not dialog.history_buttons[2].isEnabled())
        dialog.history_search.clear()
        app.processEvents()
        checks["clear_restores_all_rows"] = table.rowCount() == 1000

        # Cleanup remains global while filtered, and declining its dry-run
        # confirmation must leave the history index byte-for-byte unchanged.
        old_record = _records(1)[0]
        old_record["session_id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "ux08-old"))
        old_record["summary"]["session_id"] = old_record["session_id"]
        old_record["recorded_at"] = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
        old_record["commit_manifest"]["session_id"] = old_record["session_id"]
        HistoryStore(root).replace_sessions([*records, old_record])
        dialog.history_records[:] = HistoryStore(root).load()
        dialog.history_search.setText(old_record["session_id"])
        app.processEvents()
        prompts = []
        history_window.ask_confirmation = lambda _qt, _parent, _title, prompt, _tr: (
            prompts.append(prompt) or False)
        prompt_template = translator.text(
            "history.cleanup_prompt", sessions="__SESSION__", logs="__LOGS__")
        expected_prompt = re.escape(prompt_template).replace(
            re.escape("__SESSION__"), r"\d+").replace(re.escape("__LOGS__"), r"\d+")
        before = (root / "index.json").read_bytes()
        dialog.cleanup_button.click()
        app.processEvents()
        checks["cleanup_is_global_and_cancel_preserves_bytes"] = (
            len(prompts) == 1 and re.fullmatch(expected_prompt, prompts[0]) is not None
            and (root / "index.json").read_bytes() == before)
        dialog.grab().save(str(options.output / f"history-{options.language}.png"))
        dialog.close()

    report = {
        "PySide6": PySide6.__version__, "python": platform.python_version(),
        "platform": platform.platform(), "qpa_platform": os.environ.get("QT_QPA_PLATFORM"),
        "screen_geometry": [app.primaryScreen().geometry().width(),
                            app.primaryScreen().geometry().height()],
        "screen_device_pixel_ratio": app.primaryScreen().devicePixelRatio(),
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "requested_window": [options.width, options.height], "history_count": 1000,
        "language": options.language,
        "checks": checks,
        "cleanup_prompt": prompts,
        "cleanup_prompt_pattern": expected_prompt,
    }
    (options.output / "history.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if options.verify:
        assert all(checks.values()), checks


if __name__ == "__main__":
    main()
