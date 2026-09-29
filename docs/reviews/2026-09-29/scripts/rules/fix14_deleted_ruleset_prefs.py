# ruff: noqa: E401, E402, E701, E702, E731, F401, F811, F841
"""FIX-14: deleting a ruleset leaves a dangling id in run_options preferences.

Run from the repository root. Read-only: uses temporary directories, never the user's data.
"""
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))
sys.path.insert(0, str(REPO))

import sys, tempfile
from pathlib import Path
from types import SimpleNamespace
import ui.rules_window as rw
from ui.rules_window import RuleWindowResult
from ui.i18n import Translator
from rules.store import RuleSet, RuleStore
from app.settings import RunSettings
from tests.support.fake_qt import make_with_table
class Storage:
    def __init__(self, root):
        self.paths = SimpleNamespace(root=root, profiles=root / "profiles", rules=root / "rules")
with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    RuleStore(root / "rules").save(RuleSet("X"))
    prefs = {"run_options": {"ruleset_ids": ["default", "X"]}}   # written by an earlier run (controller.py:333)
    st = RunSettings(Storage(root), SimpleNamespace(book_fingerprint=lambda: "B"), prefs, language="en", session_id="1")
    print("session 1 active:", st.active.ruleset_ids, "| profile saved:", st.active_profile_is_saved)
    rw.show_rules_window = lambda *a, **k: RuleWindowResult("default", (RuleSet("default"),),
                                                             run_ruleset_ids=("default",), deleted=("X",))
    st.edit_rules("s2t", Translator("en"), make_with_table(), None)
    print("after delete: active:", st.active.ruleset_ids, "| X.json exists:", (root / "rules" / "X.json").exists())
    # user cancels the run -> controller only writes {"ui": ...}; preferences keep X
    st2 = RunSettings(Storage(root), SimpleNamespace(book_fingerprint=lambda: "B"), prefs, language="en", session_id="2")
    print("next launch: missing-ruleset notice =", st2.take_missing_rulesets_notice())
