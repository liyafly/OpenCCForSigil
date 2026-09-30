# ruff: noqa: E402
"""FU-02: rename 'default' to X, then delete X -> StopIteration in the Qt slot.

Run from the repository root. Read-only: no files are written.
"""
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))
sys.path.insert(0, str(REPO))

from types import SimpleNamespace

from rules.models import Rule
from rules.store import RuleSet
from tests.support.fake_qt import make_with_table
from ui import rules_window
from ui.i18n import Translator
from ui.rules_window import RuleManagerDialog

qt = make_with_table()
qt.QInputDialog = SimpleNamespace(getText=lambda *_args, **_kwargs: ("X", True))
rule = Rule(id="d1", source="旧", target="舊", direction="s2t")
manager = RuleManagerDialog(
    qt, (rule,), translator=Translator("en"), config="s2t",
    rulesets=(RuleSet("default", (rule,)),), ruleset_id="default", run_ruleset_ids=("default",))
manager._rename_ruleset()
print("after rename:", list(manager._rulesets), "| delete enabled:",
      manager._ruleset_menu_actions["delete"].isEnabled()
      if hasattr(manager, "_ruleset_menu_actions") else "n/a")
rules_window.ask_confirmation = lambda *_args, **_kwargs: True
try:
    manager._delete_ruleset()
    print("after delete:", list(manager._rulesets), "| current =", manager._ruleset_id,
          "| rules =", manager.rules)
except Exception as exc:  # noqa: BLE001
    print("EXCEPTION escapes _delete_ruleset:", type(exc).__name__, exc,
          "| rulesets left =", list(manager._rulesets))
