# ruff: noqa: E402,E702
"""RULE-01: regex hit budget counts overlapping candidates and is per whole book."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace
REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))

from core.models import ConvertRequest, RuleSnapshot as ReqSnap
from core.workflow import ConversionWorkflow
from rules.matching import RegexBudget, collect_matches, replace_stage, RuleExecutionError
from rules.models import Rule, RuleSnapshot
from rules.regex_runtime import load_regex_module
from sigil.adapter import SigilBookAdapter


class Backend:
    config = "s2t"
    def convert(self, text): return text
    def convert_for_config(self, _c, text): return text
    def provenance(self): return SimpleNamespace(as_dict=lambda: {"backend": "fake"})


class MultiBook:
    def __init__(self, sources): self.sources = dict(sources); self.writes = {}
    def text_iter(self): return iter((k, f"{k}.xhtml") for k in self.sources)
    def readfile(self, k): return self.sources[k]
    def writefile(self, k, s): self.writes[k] = s


def rule(**kw):
    base = dict(semantic_version=2, type="exact", action="replace", match_type="regex",
                stage="post", direction="*", scope="global")
    base.update(kw)
    return Rule.from_dict(base)


regex = load_regex_module()
# (a) one run of 6 Han characters, one real replacement, but how many "hits" are counted?
r = rule(id="han", source=r"\p{Han}+", target="X")
budget = RegexBudget()
cands = collect_matches("你好世界再见", (r,), {"han": regex.compile(r.source, regex.VERSION1)}, budget)
applied_budget = RegexBudget()
_result, applied = replace_stage(
    "你好世界再见", (r,), {"han": regex.compile(r.source, regex.VERSION1)}, applied_budget)
print("(a) text='你好世界再见' pattern=\\p{Han}+ -> candidates:", len(cands),
      "budget.regex_hits:", applied_budget.regex_hits,
      "(only", len(applied), "replacement is applied)")

# (b) a single 600-character paragraph aborts the analysis.
try:
    budget = RegexBudget()
    collect_matches("汉" * 600, (r,), {"han": regex.compile(r.source, regex.VERSION1)}, budget)
    print("(b) 600-char paragraph: OK")
except RuleExecutionError as exc:
    print("(b) 600-char paragraph:", type(exc).__name__, exc)

# (c) A user regex that collapses horizontal spaces on a normal multi-file book:
#     60 files x 10 paragraphs, each paragraph has one double space -> 600 real matches.
spaces = Rule.from_dict(dict(
    id="spaces", semantic_version=2, type="exact", action="replace",
    match_type="regex", stage="post", source=r"[ \t\u3000]{2,}", target=" ",
    direction="*", scope="global"))
frozen = RuleSnapshot.freeze((spaces,))
request = ConvertRequest("s2t", rules_snapshot=ReqSnap(rules_hash=frozen.sha256, rules=frozen.rules),
                         quotation_mode="keep", diagnose_mixed=False, detailed_classification=False)
sources = {f"c{i:03d}": "<html><body>" + "".join("<p>甲  乙</p>" for _ in range(10)) + "</body></html>"
           for i in range(60)}
flow = ConversionWorkflow(SigilBookAdapter(MultiBook(sources)), Backend(), request)
try:
    planned = flow.plan()
    print("(c) 60 files x 10 paragraphs with one double space: planned", len(planned), "files")
except Exception as exc:
    print("(c) 60 files x 10 paragraphs with one double space:", type(exc).__name__, str(exc)[:200])

# (d) Same book but only 40 files (400 matches) succeeds -> the limit is per whole book, per rule.
flow = ConversionWorkflow(SigilBookAdapter(MultiBook(dict(list(sources.items())[:40]))), Backend(), request)
planned = flow.plan()
print("(d) 40 files:", sum(len(p.plan.changes) for p in planned), "changes, OK")
