# ruff: noqa: E401, E402, E701, E702, E731, F401, F811, F841
"""FIX-16: clicking the foreign-owner banner shows unrelated rules.

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
rules = (Rule(id="f", source="乾", target="幹", direction="s2t", scope="book", book_fingerprint="OLD"),
         *(Rule(id=f"n{i}", source=f"词{i}", target=f"詞{i}", direction="s2t") for i in range(9)))
for run in (("A",), ()):
    m = RuleManagerDialog(make_with_table(), rules, translator=Translator("zh-Hans"), config="s2t",
                          profile_id="P", book_fingerprint="CUR", rulesets=(RuleSet("A", rules),),
                          ruleset_id="A", run_ruleset_ids=run)
    m.foreign_owner_button.click()
    print("run_ids=%r banner=%r -> visible after click: %d rules" % (run, m.foreign_owner_button.text(), len(m._visible_rule_ids)))
