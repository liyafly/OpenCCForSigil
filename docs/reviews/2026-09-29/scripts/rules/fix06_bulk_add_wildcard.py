# ruff: noqa: E401, E402, E701, E702, E731, F401, F811, F841
"""FIX-06: bulk add inherits the editor's '*' direction.

Run from the repository root. Read-only: uses temporary directories, never the user's data.
"""
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))
sys.path.insert(0, str(REPO))

import sys
from pathlib import Path
from tests.support.fake_qt import make_with_table
from ui.i18n import Translator
import ui.rules_window as rules_window
from ui.rules_window import RuleManagerDialog
m = RuleManagerDialog(make_with_table(), (), translator=Translator("zh-Hans"), config="s2t")
m.direction_combo.setCurrentIndex(m.direction_combo.findData("*"))
reviews = []
m._confirm_import = lambda review: (reviews.append(review), True)[1]
def accept(dialog):
    editor = next(c for c in dialog._layout.children if isinstance(c, m._qt.QPlainTextEdit))
    editor.setPlainText("里=裡\n软件=軟體")
    dialog._layout.children[-1].children[-1].clicked.emit()
rules_window.exec_dialog = accept
m._bulk_add()
print("editor direction '*': bulk-added", [(r.direction, r.source, r.target) for r in m.rules])
