# ruff: noqa: E402
"""FIX-11: zero-count fragments in the batch feedback line and in the result box.

Run from the repository root. Uses fake Qt, never the user's data. Prints every line
that still contains a standalone zero count; after the fix it must print "none" for
every scenario.
"""
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))
sys.path.insert(0, str(REPO))

from tests.support.fake_qt import make_with_table
from tests.unit.test_preview_batch import _entries
from ui import preview_window
from ui.i18n import Translator
from ui.preview_window import _PreviewDialog

ZERO = re.compile(r"(?<![\d.])0(?!\d)")


def zero_lines(text):
    found = [line for line in text.splitlines() if ZERO.search(line)]
    return found or "none"


print("== UXS-03 batch feedback after 'Resolve remaining' (no linked groups) ==")
for language in ("en", "zh-Hans", "zh-Hant"):
    entries, sessions, _groups, _files = _entries(
        [(f"c{i}", "book", None) for i in range(10)])
    planned = (SimpleNamespace(
        source=SimpleNamespace(file_id="book", href="Text/book.xhtml", document_kind="xhtml"),
        plan=sessions[0].plan),)
    dialog = _PreviewDialog(make_with_table(), planned, sessions, Translator(language), None)
    preview_window.exec_dialog = lambda _batch_dialog: 1
    dialog._open_batch_decision(initial_scope="all")
    print(language, "feedback:", repr(dialog._last_group_feedback),
          "| zero lines:", zero_lines(dialog._last_group_feedback))


class _Box:
    messages = []

    @classmethod
    def information(cls, _parent, _title, message):
        cls.messages.append(message)

    warning = information


preview_window.load_qt = lambda: type("FakeQt", (), {"QMessageBox": _Box})
preview_window.ensure_application = lambda *_a, **_k: None

print("\n== UXS-08 result box (non-cancel) ==")
scenarios = {
    "success, nothing skipped, 1 unchanged-only file": dict(
        files_scanned=3, files_changed=2, accepted_changes=5, skipped_changes=0,
        files_not_written=1, files_without_changes=0),
    "no-op, every file unchanged": dict(
        files_scanned=3, files_changed=0, accepted_changes=0, skipped_changes=0,
        files_not_written=3, files_without_changes=3),
    "all skipped": dict(
        files_scanned=2, files_changed=0, accepted_changes=0, skipped_changes=4,
        files_not_written=2, files_without_changes=0, files_all_skipped=2),
}
for language in ("en", "zh-Hans", "zh-Hant"):
    for name, values in scenarios.items():
        _Box.messages = []
        preview_window.show_result(status="success", translator=Translator(language), **values)
        print(language, "|", name, "| zero lines:", zero_lines(_Box.messages[0]))
