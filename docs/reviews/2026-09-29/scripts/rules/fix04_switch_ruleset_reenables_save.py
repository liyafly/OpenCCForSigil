# ruff: noqa: E401, E402, E701, E702, E731, F401, F811, F841
"""FIX-04: viewing an uninvolved run ruleset re-enables Save while a run conflict exists.

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
from rules.models import Rule
from rules.store import RuleSet
from rules.conflicts import blocking_conflicts
from tests.support.fake_qt import make_with_table
from ui.i18n import Translator
from ui.rules_window import RuleManagerDialog

b = Rule(id="b1", direction="s2t", source="软件", target="軟件")
sets = (RuleSet("A", (), name="A"), RuleSet("B", (b,), name="B"), RuleSet("C", (), name="C"))
m = RuleManagerDialog(make_with_table(), (), translator=Translator("en"), config="s2t",
                      rulesets=sets, ruleset_id="A", run_ruleset_ids=("A", "B", "C"))
m.source_edit.setText("软件"); m.target_edit.setText("軟體"); m.add_button.click()
print("viewing A: conflicts", m.conflict_list.count(), "save enabled", m.apply_button.isEnabled())
m.ruleset_combo.setCurrentIndex(m.ruleset_combo.findData("C"))
print("viewing C: conflicts", m.conflict_list.count(), "save enabled", m.apply_button.isEnabled())
m.apply_button.click()
saved = {rs.id: rs.rules for rs in m.result.rulesets}
print("saved result accepted:", m.accepted, "| run ids:", m.result.run_ruleset_ids)
print("blocking conflicts in saved run sets:", [[r.id for r in c.rules] for c in blocking_conflicts([*saved["A"], *saved["B"]])])
