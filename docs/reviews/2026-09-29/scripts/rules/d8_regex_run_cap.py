# ruff: noqa: E401, E402, E701, E702, E731, F401, F811, F841
"""D8: the 100,000 per-run hit cap stops the built-in collapse-spaces template on a long novel.

Run from the repository root. Read-only: uses temporary directories, never the user's data.
"""
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))
sys.path.insert(0, str(REPO))

import sys, time
from pathlib import Path
from rules.matching import RegexBudget, replace_stage, RuleExecutionError
from rules.models import Rule
from rules.templates import collapse_horizontal_spaces
from rules.regex_runtime import load_regex_module
regex = load_regex_module()
values = collapse_horizontal_spaces(1); values.update(id="collapse", direction="*", scope="global")
rule = Rule.from_dict(values)
patterns = {rule.id: regex.compile(rule.source, regex.VERSION1)}
budget = RegexBudget()
para = "　　" + "他走进房间看了一眼窗外的雨然后坐下来开始写信" * 2   # ~50 chars
try:
    for i in range(120_000):
        replace_stage(para, (rule,), patterns, budget)
    print("ok", budget.regex_hits)
except RuleExecutionError as exc:
    print(f"FAILED at paragraph {i+1} (~{(i+1)*len(para)/1e6:.1f}M chars): {exc}")
