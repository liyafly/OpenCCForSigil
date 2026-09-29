# ruff: noqa: E402,E701,E702,E731
"""RULE-15: zero-width regex passes validation, then aborts the analysis; plus entity/inline-tag probes."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace
REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))
from core.models import ConvertRequest, RuleSnapshot as ReqSnap
from core.converter import OfficialBackendConverter
from core.preview import PreviewSession
from core.workflow import ConversionWorkflow
from rules.models import Rule, RuleSnapshot
from rules.validators import validate_rules
from sigil.adapter import SigilBookAdapter

class Backend:
    config = "s2t"
    def convert(self, t): return t.replace("汉", "漢")
    def convert_for_config(self, c, t): return t
    def provenance(self): return SimpleNamespace(as_dict=lambda: {"b": 1})
class Book:
    def __init__(self, s): self.s = s; self.w = []
    def text_iter(self): yield "a", "a.xhtml"
    def readfile(self, _): return self.s
    def writefile(self, _, s): self.w.append(s)

def run(src, *rules):
    fr = RuleSnapshot.freeze(rules)
    req = ConvertRequest("s2t", rules_snapshot=ReqSnap(rules_hash=fr.sha256, rules=fr.rules),
                         quotation_mode="keep", diagnose_mixed=False, detailed_classification=False)
    flow = ConversionWorkflow(SigilBookAdapter(Book(src)), Backend(), req)
    planned = flow.plan()
    pv = [PreviewSession(p.plan) for p in planned]
    for p in pv: p.accept_all()
    staged = flow.stage(flow.finalize(pv)); flow.verify(staged)
    return staged[0].converted if staged else src + "   (no change planned)"

R = lambda **k: Rule(direction="s2t", **k)
print("entity A&amp;B, rule 'A&B'->X :", run("<html><body><p>A&amp;B 汉</p></body></html>", R(id="e", source="A&B", target="X")))
print("numeric &#x6C49;字, rule '汉字'->Y:", run("<html><body><p>&#x6C49;字</p></body></html>", R(id="n", source="汉字", target="Y")))
print("inline tag 乾<b>隆</b>, protect 乾隆:", run("<html><body><p>乾<b>隆</b></p></body></html>", R(id="p", type="protect", source="乾隆")))
print("title attr, rule applies to attributes too:", run('<html><body><p title="软件">软件</p></body></html>', R(id="t", source="软件", target="軟體")))

# zero-width at runtime
z = Rule.from_dict(dict(id="z", semantic_version=2, type="exact", action="replace", match_type="regex",
                        stage="pre", direction="*", source="(?<=「)[^」]*", target="…"))
print("validation of (?<=「)[^」]*:", "passes" if validate_rules((z,)) else "")
try:
    zero_snapshot = RuleSnapshot.freeze((z,))
    zero_request = ConvertRequest(
        "s2t",
        rules_snapshot=ReqSnap(rules_hash=zero_snapshot.sha256, rules=zero_snapshot.rules),
        detailed_classification=False,
        diagnose_mixed=False,
        include_rule_trace=True,
    )
    result = OfficialBackendConverter(Backend()).convert("他说「」然后", zero_request)
    print(result.target, "zero-width skips:", result.zero_width_skips)
except Exception as exc:
    print("runtime on '他说「」然后':", type(exc).__name__, exc)
