# ruff: noqa: E401, E402, E701, E702, E731, F401, F811, F841
"""FIX-06: after removing a '*' rule the next new rule silently inherits '*'.

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
from ui.rules_window import RuleManagerDialog
from ui.i18n import Translator
from rules.models import Rule
from rules.store import RuleSet
w0 = Rule(id="w", source="里", target="裡", direction="*")
m = RuleManagerDialog(make_with_table(), (w0,), translator=Translator("en"), config="s2t",
                      rulesets=(RuleSet("default", (w0,)),), ruleset_id="default", run_ruleset_ids=("default",))
print("fresh editor direction:", m.direction_combo.currentData())
m.table.selectRow(0); m._load_selected(); m._remove()
print("after selecting '*' rule and removing it, editor direction:", m.direction_combo.currentData())
m.source_edit.setText("面"); m.target_edit.setText("麵"); m._add()
print("next new rule direction:", m.rules[-1].direction)
