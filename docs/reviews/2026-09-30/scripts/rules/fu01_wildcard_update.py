# ruff: noqa: E402
"""FU-01: updating an existing '*' rule twice silently turns it into s2t.

Run from the repository root. Read-only: no files are written.
"""
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))
sys.path.insert(0, str(REPO))

from rules.models import Rule
from rules.store import RuleSet
from tests.support.fake_qt import make_with_table
from ui.i18n import Translator
from ui.rules_window import RuleManagerDialog

rule = Rule(id="w", source="里", target="裡", direction="*")
manager = RuleManagerDialog(
    make_with_table(), (rule,), translator=Translator("en"), config="s2t",
    rulesets=(RuleSet("default", (rule,)),), ruleset_id="default", run_ruleset_ids=("default",))
manager.table.selectRow(0)
manager._load_selected()
print("loaded: combo =", manager.direction_combo.currentData(), "| editing =", manager._editing_rule_id)
manager.target_edit.setText("裏")
manager._update_selected()
print("after 1st update: rule =", manager.rules[0].direction,
      "| combo =", manager.direction_combo.currentData(), "| editing =", manager._editing_rule_id)
manager.target_edit.setText("裡")
manager._update_selected()
print("after 2nd update: rule =", manager.rules[0].direction)
