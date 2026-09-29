# ruff: noqa: E401, E402, E701, E702, E731, F401, F811, F841
"""D8: many fragments are not stopped by a book-wide regex hit cap.

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
from rules.regex_runtime import load_regex_module
regex = load_regex_module()
rule = Rule.from_dict(dict(
    id="collapse", semantic_version=2, type="exact", action="replace",
    match_type="regex", stage="post", source=r"[ \t\u3000]{2,}", target=" ",
    direction="*", scope="global"))
patterns = {rule.id: regex.compile(rule.source, regex.VERSION1)}
budget = RegexBudget()
para = "　　" + "他走进房间看了一眼窗外的雨然后坐下来开始写信" * 2   # ~50 chars
try:
    for i in range(120_000):
        replace_stage(para, (rule,), patterns, budget)
    print("ok", i + 1)
except RuleExecutionError as exc:
    print(f"FAILED at paragraph {i+1} (~{(i+1)*len(para)/1e6:.1f}M chars): {exc}")
