# ruff: noqa: E402
"""FU-04: the rule test output lists the final result twice with different separators.

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

for language in ("zh-Hans", "en"):
    rule = Rule(id="r1", source="软件", target="軟體", direction="s2t")
    manager = RuleManagerDialog(
        make_with_table(), (rule,), translator=Translator(language), config="s2t",
        official_convert=lambda _config, text: text.replace("软件", "軟件"),
        rulesets=(RuleSet("default", (rule,)),), ruleset_id="default",
        run_ruleset_ids=("default",))
    manager.test_input.setPlainText("软件")
    manager._test()
    label = Translator(language).text("rules.final_label")
    lines = [line for line in manager.test_output.toPlainText().splitlines()
             if line.startswith(label)]
    print(language, "final-result lines:", lines)
