# ruff: noqa: E402,E702,E741
import sys
import json
import tempfile
from pathlib import Path
from pathlib import Path as _P; _ROOT = _P(__file__).resolve().parents[5]; sys.path.insert(0, str(_ROOT / "plugin/OpenCCForSigil"))
sys.path.insert(0, str(_ROOT / "docs/reviews/2026-09-27/ui-workflow/scripts"))
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from ui.qt import load_qt, ensure_application
from ui import history_window
from logging_ext.history import HistoryStore
from check_history_layout import _records
qt = load_qt(); app = ensure_application(qt)
with tempfile.TemporaryDirectory() as t:
    root = Path(t) / "history"
    HistoryStore(root).replace_sessions(_records(20))
    opened = []
    dialog = history_window.show_history(root, language="zh-Hans", on_inspect=opened.append,
                                         on_export=lambda *a: None, qt_widgets=qt)
    dialog.show(); app.processEvents()
    dialog.history_table.selectRow(0); app.processEvents()
    dialog.history_search.setFocus()
    QTest.keyClicks(dialog.history_search, "Book")
    app.processEvents()
    QTest.keyClick(dialog.history_search, Qt.Key_Return)
    app.processEvents()
    print(json.dumps({"inspect_called_by_enter_in_search": len(opened),
                      "visible_rows": dialog.history_table.rowCount(),
                      "buttons": [b.text() for b in dialog.history_buttons],
                      "labels": [l.text() for l in dialog.findChildren(qt.QLabel) if l.isVisible()]}, ensure_ascii=False, indent=1))
