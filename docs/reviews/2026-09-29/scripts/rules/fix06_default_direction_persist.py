# ruff: noqa: E401, E402, E701, E702, E731, F401, F811, F841
"""FIX-06: default_direction persisted from an s2t session is preselected in a later t2s session.

Run from the repository root. Read-only: uses temporary directories, never the user's data.
"""
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))
sys.path.insert(0, str(REPO))

import sys, tempfile, json
from pathlib import Path
from types import SimpleNamespace
from tests.support.fake_qt import make_with_table
import ui.rules_window as rw
from ui.rules_window import RuleManagerDialog
from ui.i18n import Translator
from app.settings import RunSettings
from rules.precedence import applies_to

class Storage:
    def __init__(self, root):
        self.paths = SimpleNamespace(root=root, profiles=root / "profiles", rules=root / "rules")
with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    st = RunSettings(Storage(root), SimpleNamespace(book_fingerprint=lambda: "B"), {}, language="en", session_id="s")
    st.bind_run(st.active, SimpleNamespace(available_configs=lambda: {"s2t", "t2s"}))
    seen = {}
    def window(rules, **kw):
        m = RuleManagerDialog(make_with_table(), rules, **kw)
        seen.setdefault("dirs", []).append((kw["config"], m.direction_combo.currentData()))
        if kw["config"] == "s2t":
            m.source_edit.setText("里"); m.target_edit.setText("裡"); m._add()
        else:
            m.source_edit.setText("後"); m.target_edit.setText("后"); m._add()
            seen["t2s_rule"] = m.rules[-1]
        m._apply(); return m.result
    rw.show_rules_window = window
    st.edit_rules("s2t", Translator("en"), make_with_table(), None)
    print("default.json default_direction after s2t session:",
          json.loads((root / "rules" / "default.json").read_text())["default_direction"])
    st.edit_rules("t2s", Translator("en"), make_with_table(), None)
    print("editor preselected direction per session (config, preselected):", seen["dirs"])
    r = seen["t2s_rule"]
    print("rule added in t2s session: direction =", r.direction, "| applies to this t2s run:", applies_to(r, config="t2s"))
