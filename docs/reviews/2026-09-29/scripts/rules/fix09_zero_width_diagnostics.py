# ruff: noqa: E401, E402, E701, E702, E731, F401, F811, F841
"""FIX-09: zero-width skip diagnostics are per fragment and not localized.

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
from types import SimpleNamespace
from core.models import ConvertRequest, RuleSnapshot as ReqSnap
from core.workflow import ConversionWorkflow
from rules.models import Rule, RuleSnapshot
from sigil.adapter import SigilBookAdapter
from ui.i18n import Translator

class Backend:
    config = "s2t"
    def convert(self, t): return t
    def convert_for_config(self, c, t): return t
    def provenance(self): return SimpleNamespace(as_dict=lambda: {"b": 1})
class MultiBook:
    def __init__(self, sources): self.sources = dict(sources)
    def text_iter(self): return iter((k, f"{k}.xhtml") for k in self.sources)
    def readfile(self, k): return self.sources[k]
    def writefile(self, k, s): pass

z = Rule.from_dict(dict(id="z", semantic_version=2, type="exact", action="replace", match_type="regex",
                        stage="pre", direction="*", source="(?<=「)[^」]*", target="…"))
fr = RuleSnapshot.freeze((z,))
req = ConvertRequest("s2t", rules_snapshot=ReqSnap(rules_hash=fr.sha256, rules=fr.rules),
                     quotation_mode="keep", diagnose_mixed=False, detailed_classification=False)
sources = {f"c{i:02d}": "<html><body>" + "".join("<p>他说「」然后「好」</p>" for _ in range(10)) + "</body></html>" for i in range(6)}
flow = ConversionWorkflow(SigilBookAdapter(MultiBook(sources)), Backend(), req)
planned = flow.plan()
total = 0
for p in planned:
    diags = [d for d in p.plan.diagnostics if getattr(d, "code", "") == "REGEX_ZERO_WIDTH_SKIPPED"]
    total += len(diags)
print("files planned:", len(planned), "changes:", sum(len(p.plan.changes) for p in planned))
print("REGEX_ZERO_WIDTH_SKIPPED diagnostics total:", total, "(6 files x 10 paragraphs, 1 rule)")
d = next(d for p in planned for d in p.plan.diagnostics if getattr(d, "code", "") == "REGEX_ZERO_WIDTH_SKIPPED")
print("sample diagnostic:", d)
for lang in ("en", "zh-Hans"):
    t = Translator(lang)
    print(lang, "name:", t.text("diagnostic.name.REGEX_ZERO_WIDTH_SKIPPED"),
          "| fallback:", t.text("diagnostic.name.unknown", code="REGEX_ZERO_WIDTH_SKIPPED"))
from ui.preview_window import _diagnostic_records
try:
    import inspect
    print("sig:", inspect.signature(_diagnostic_records))
except Exception as e:
    print(e)
recs = _diagnostic_records(planned, Translator("zh-Hans"))
zr = [r for r in recs if r.code == "REGEX_ZERO_WIDTH_SKIPPED"]
print("preview records for zero-width:", len(zr))
print("first record:", zr[0])
