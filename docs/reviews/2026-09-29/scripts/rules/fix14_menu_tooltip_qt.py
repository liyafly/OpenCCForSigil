# ruff: noqa: E401, E402, E701, E702, E731, F401, F811, F841
"""FIX-14: the 'cannot delete default' tooltip is invisible in the menu (real Qt).

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
from ui.qt import ensure_application, load_qt
qt = load_qt(); app = ensure_application(qt)
from ui.rules_window import RuleManagerDialog
from ui.i18n import Translator
from rules.store import RuleSet
from rules.models import Rule
w = RuleManagerDialog(qt, (), translator=Translator("zh-Hans"), config="s2t", profile_id="P", book_fingerprint="B",
    rulesets=(RuleSet("default"), RuleSet("A", (Rule(id="a1", source="软件", target="軟體", direction="s2t"),))),
    ruleset_id="default", run_ruleset_ids=("default",))
act = w._ruleset_menu_actions["delete"]
print("delete action enabled:", act.isEnabled(), "| tooltip:", act.toolTip(),
      "| menu.toolTipsVisible():", w.ruleset_menu.toolTipsVisible())
print("menu actions:", [a.text() for a in w.ruleset_menu.actions()])
print("ruleset row widgets:", [type(x).__name__ + ":" + (x.text() if hasattr(x, "text") else "")
      for x in (w.new_ruleset_button, w.rename_ruleset_button, w.ruleset_more_button, w.use_in_run_check)])
print("ruleset_enabled_check parent is settings dialog:",
      w.ruleset_enabled_check.window() is w.ruleset_settings_dialog)
