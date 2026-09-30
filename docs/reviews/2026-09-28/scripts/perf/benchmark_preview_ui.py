#!/usr/bin/env python3
"""Real-Qt main-thread latency of the preview dialog on a synthetic large book.

Run from the repository root:

    QT_QPA_PLATFORM=offscreen mise exec -- uv run --with PySide6==6.11.2 \
        python <this script> --output /tmp/opencc-preview-ui.json

The plan is built once with the vendored OpenCC backend (not timed here).
Every interaction below is a main-thread call measured with perf_counter,
including the Qt event processing it triggers. No EPUB is written.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import gc
import json
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synthetic_book import ROOT, SyntheticBook, build_sources  # noqa: E402

from core.models import ConvertRequest  # noqa: E402
from core.preview import PreviewSession  # noqa: E402
from core.workflow import ConversionWorkflow  # noqa: E402
from opencc_backend.backend import OpenCCBackend  # noqa: E402
from sigil.adapter import SigilBookAdapter  # noqa: E402
from ui import preview_window as pw  # noqa: E402
from ui.i18n import Translator  # noqa: E402
from ui.qt import ensure_application, load_qt  # noqa: E402


def timed(fn, app):
    gc.collect()
    start = time.perf_counter()
    fn()
    app.processEvents()
    return time.perf_counter() - start


def median_of(fn, app, repeats):
    samples = [timed(fn, app) for _ in range(repeats)]
    return round(statistics.median(samples), 4), [round(value, 4) for value in samples]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", type=int, default=200)
    parser.add_argument("--paragraphs", type=int, default=60)
    parser.add_argument("--chars", type=int, default=150)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    sources = build_sources(args.files, args.paragraphs, args.chars)
    workflow = ConversionWorkflow(SigilBookAdapter(SyntheticBook(sources)),
                                  OpenCCBackend("s2t"), ConvertRequest("s2t"))
    planned = workflow.plan()
    qt = load_qt()
    app = ensure_application(qt, language="en")
    translator = Translator("en")
    results = {"changes": sum(len(item.plan.changes) for item in planned),
               "diagnostics": sum(len(item.plan.diagnostics) for item in planned)}

    start = time.perf_counter()
    records = pw._diagnostic_records(planned, translator)
    results["diagnostic_records_seconds"] = round(time.perf_counter() - start, 4)
    results["diagnostic_records"] = len(records)

    previews = tuple(PreviewSession(item.plan) for item in planned)
    start = time.perf_counter()
    dialog = pw._PreviewDialog(qt, planned, previews, translator, None)
    results["dialog_construct_seconds"] = round(time.perf_counter() - start, 4)
    results["first_show_seconds"] = round(timed(dialog.dialog.show, app), 4)

    counters = {"decision": 0}
    original_decision = PreviewSession.decision

    def counting_decision(self, change_id):
        counters["decision"] += 1
        return original_decision(self, change_id)

    PreviewSession.decision = counting_decision

    def measure(label, fn, repeats=args.repeats):
        counters["decision"] = 0
        value, samples = median_of(fn, app, repeats)
        results[label] = {"median_seconds": value, "samples": samples,
                          "decision_calls_per_action": counters["decision"] // repeats}

    # Ordinary single-change decisions with no filter.
    dialog._set_current_row(0)
    measure("accept_this_no_filter", dialog._accept_this, repeats=args.repeats * 4)

    # Status filter "undecided" is active: every decision rebuilds visible rows.
    index = dialog.status_filter.findData("undecided")
    dialog.status_filter.setCurrentIndex(index)
    app.processEvents()
    measure("accept_this_status_undecided", dialog._accept_this)
    dialog.status_filter.setCurrentIndex(0)
    app.processEvents()

    # Text search over all rows (query typed after the 140 ms debounce).
    def search():
        dialog.search_input.setText("軟件")
        dialog._refresh()

    measure("search_refresh", search, repeats=3)
    dialog._clear_filters()
    app.processEvents()

    def resolve_batch(scope, *, action="accept", only_undecided=False):
        def confirm_batch():
            modal = app.activeModalWidget()
            assert modal is not None
            combos = modal.findChildren(qt.QComboBox)
            only_check = modal.findChild(qt.QCheckBox)
            assert len(combos) == 2 and only_check is not None
            combos[0].setCurrentIndex(combos[0].findData(scope))
            combos[1].setCurrentIndex(combos[1].findData(action))
            only_check.setChecked(only_undecided)
            prefixes = tuple(
                translator.text(key).split("{")[0]
                for key in (
                    "preview.batch_confirm", "preview.batch_confirm_overwrite",
                    "preview.batch_confirm_none",
                )
            )
            buttons = modal.findChildren(qt.QPushButton)
            confirm = next(button for button in buttons
                           if any(button.text().startswith(prefix) for prefix in prefixes))
            if confirm.isEnabled():
                confirm.click()
            else:
                next(button for button in buttons
                     if button.text() == translator.text("common.cancel")).click()

        qt.QTimer.singleShot(0, confirm_batch)
        dialog._open_batch_decision(initial_scope=scope)

    dialog._set_current_row(len(dialog._entries) // 2)
    measure("batch_current_file", lambda: resolve_batch("file"), repeats=3)
    measure("undo_after_current_file_batch", dialog._undo_preview_action, repeats=1)
    measure("batch_all_changes", lambda: resolve_batch("all"), repeats=1)
    measure("undo_all_changes_batch", dialog._undo_preview_action, repeats=1)

    # Attach synthetic two-row rule groups to otherwise unchanged preview rows.
    # This isolates the grouped-decision path while retaining the full book size.
    group_count = min(max(args.repeats, 1), len(dialog._entries) // 2)
    if group_count:
        entries = list(dialog._entries)
        grouped_entries = {}
        grouped_file_ids = {}
        grouped_stats = {}
        for group_index in range(group_count):
            group_id = f"rules:benchmark-occurrence-{group_index}"
            first = group_index * 2
            pair = []
            for row in (first, first + 1):
                preview, change = entries[row]
                updated = (preview, replace(change, group_id=group_id))
                entries[row] = updated
                pair.append(updated)
            grouped_entries[group_id] = tuple(pair)
            file_id = pair[0][1].file_id
            grouped_file_ids[group_id] = frozenset((file_id,))
            grouped_stats[group_id] = (2, 1)
        dialog._entries = tuple(entries)
        dialog._entry_position = {
            (change.file_id, change.change_id): index
            for index, (_preview, change) in enumerate(dialog._entries)
        }
        dialog._visible_entries_cache = dialog._entries
        dialog._visible_positions = list(range(len(dialog._entries)))
        dialog._group_entries_by_id.update(grouped_entries)
        dialog._group_file_ids.update(grouped_file_ids)
        dialog._group_stats.update(grouped_stats)
        dialog.table_model.set_entries(dialog._entries)
        index = dialog.status_filter.findData("undecided")
        dialog.status_filter.setCurrentIndex(index)
        app.processEvents()

        def accept_group():
            dialog._set_current_row(0)
            dialog._accept_this()

        measure("accept_group_status_undecided", accept_group, repeats=group_count)
    else:
        results["accept_group_status_undecided"] = {"skipped": "fewer than two changes"}

    PreviewSession.decision = original_decision
    dialog._allow_reject = True
    dialog.dialog.reject() if hasattr(dialog.dialog, "reject") else None
    output = {
        "head": subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                        text=True).strip(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "qt_platform": app.platformName(),
        "results": results,
    }
    text = json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
