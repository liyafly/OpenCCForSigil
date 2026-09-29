# ruff: noqa: E401, E402, E701, E702, E731, F401, F811, F841
"""FIX-17: a single catastrophic regex search still stops at the 50 ms timeout.

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
r = Rule(id="evil", semantic_version=2, action="replace", stage="pre", match_type="regex",
         direction="s2t", source=r"(a|aa)+$", target="x")
t0 = time.perf_counter()
try:
    replace_stage("a" * 40 + "b", (r,), {r.id: regex.compile(r.source, regex.VERSION1)}, RegexBudget())
    print("no error")
except RuleExecutionError as exc:
    print(f"RuleExecutionError after {time.perf_counter()-t0:.3f}s: {exc}")
