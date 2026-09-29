# ruff: noqa: E402
"""RULE-13: the inline rule test uses the visible selected rule as empty input."""
import os
import sys
from pathlib import Path
REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))
sys.path.insert(0, str(REPO))

from rules.models import Rule
from tests.support.fake_qt import make_with_table
from ui import rules_window
from ui.i18n import Translator
from ui.rules_window import RuleManagerDialog

seen = {}
inspect_dictionary = rules_window.inspect_dictionary


def capture_input(text, **kwargs):
    seen["text"] = text
    return inspect_dictionary(text, **kwargs)


rules_window.inspect_dictionary = capture_input
rules = (Rule(id="r-a", direction="s2t", source="甲方", target="甲方案"),
         Rule(id="r-b", direction="s2t", source="乙方", target="乙方案"))
w = RuleManagerDialog(make_with_table(), rules, translator=Translator("zh-Hans"),
                      official_convert=lambda _c, v: v, config="s2t")
w.search_edit.setText("乙方")          # filter: only r-b is visible, at table row 0
w._filters_changed()
w.table.selectRow(0)
w._load_selected()
print("visible rows:", w._visible_rule_ids, "| editor shows:", w.source_edit.text())
w._test()
print("rule test input:", seen.get("text"), "(expected 乙方)")
