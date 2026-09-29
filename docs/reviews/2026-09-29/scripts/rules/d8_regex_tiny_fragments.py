# ruff: noqa: E401, E402, E701, E702, E731, F401, F811, F841
"""D8: many small fragments are no longer limited by an analysis-wide time budget.

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

def run(k_rules, n_fragments, frag_len):
    rules = tuple(Rule(id=f"re{i}", semantic_version=2, action="replace", stage="pre",
                       match_type="regex", direction="s2t", source=f"甲{i}[乙丙]+丁", target="戊")
                  for i in range(k_rules))
    patterns = {r.id: regex.compile(r.source, regex.VERSION1) for r in rules}
    budget = RegexBudget()
    text = ("第一章节标题内容正文" * 10)[:frag_len]
    t0 = time.perf_counter()
    try:
        for i in range(n_fragments):
            replace_stage(text, rules, patterns, budget)
        outcome = "ok"
    except RuleExecutionError as exc:
        outcome = f"FAILED after {i} fragments: {exc}"
    return (f"rules={k_rules} fragments={n_fragments} len={frag_len} "
            f"wall={time.perf_counter()-t0:.1f}s -> {outcome}")

for args in [(128, 60_000, 8), (128, 60_000, 150), (32, 60_000, 8), (128, 20_000, 8)]:
    print(run(*args), flush=True)
