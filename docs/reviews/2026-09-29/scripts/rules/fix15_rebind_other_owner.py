# ruff: noqa: E401, E402, E701, E702, E731, F401, F811, F841
"""FIX-15: window rebind keeps the stale other owner; import rebind clears it.

Run from the repository root. Read-only: uses temporary directories, never the user's data.
"""
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))
sys.path.insert(0, str(REPO))

import sys, json
from pathlib import Path
from tests.support.fake_qt import make_with_table
from ui.rules_window import RuleManagerDialog
from ui.i18n import Translator
from rules.importers import import_rules
from rules.models import Rule
from rules.store import RuleSet
# (2) book rule that also carries a stale profile owner (what TSV import still produces)
b = Rule(id="bp", source="术语", target="專名", direction="s2t", scope="book",
         book_fingerprint="OLD-BOOK", profile_id="OLD-PROFILE")
w = RuleManagerDialog(make_with_table(), (b,), translator=Translator("en"), config="s2t",
                      profile_id="P", book_fingerprint="CUR", rulesets=(RuleSet("default", (b,)),),
                      ruleset_id="default", run_ruleset_ids=("default",))
w.table.selectRow(0); w._load_selected(); w.rebind_owner_button.click()
print("(2) after window rebind: book=%r profile=%r" % (w.rules[0].book_fingerprint, w.rules[0].profile_id))
from rules.exporters import export_rules
rb = import_rules(export_rules((b,), format="json"), format="json", scope="book", profile_id="P",
                  book_fingerprint="CUR", rebind_owner=True).rules[0]
print("    after import rebind: book=%r profile=%r" % (rb.book_fingerprint, rb.profile_id))
