# ruff: noqa: E402,E702
"""Areas checked fine: Ext-B/emoji, source==target, empty/whitespace sources, no cascade, TXT BOM/CRLF, TSV roundtrip."""
import os
import sys
from pathlib import Path
REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))
from rules.engine import convert_with_overlay
from rules.models import Rule, RuleSnapshot
from rules.validators import validate_rules, RuleValidationError
from rules.conflicts import find_conflicts
from rules.exporters import export_rules
from rules.importers import import_rules

def run(text, *rules):
    try:
        r = convert_with_overlay(text, lambda s: s.replace("发", "發"), config="s2t", snapshot=RuleSnapshot.freeze(rules))
        return r.final, len(r.changes), r.reconstruct() == r.final
    except Exception as e:
        return type(e).__name__ + ": " + str(e)[:90]
V2 = dict(semantic_version=2, action="override", stage="source")
print("ExtB literal:", run("𠀀发𠀀", Rule(id="x", direction="s2t", source="𠀀", target="😀")))
print("emoji source:", run("a😀b", Rule(id="x", direction="s2t", source="😀", target="笑")))
print("source==target exact (V1):", run("发", Rule(id="x", direction="s2t", source="发", target="发")))
for label, kw in (("empty source", dict(source="", target="x")),
                  ("whitespace V1 source", dict(source="  ", target="x")),
                  ("whitespace V2 source", dict(source="  ", target="x", **V2)),
                  ("punct-only V1 source", dict(source="，", target=",")),
                  ("punct-only V2 source", dict(source="，", target=",", **V2))):
    try:
        validate_rules((Rule(id="x", direction="s2t", **kw),)); print(label, "-> accepted")
    except RuleValidationError as e:
        print(label, "-> rejected:", e)
print("chaining A->B, B->C (same stage):", run("AB", Rule(id="1", direction="s2t", source="A", target="B"),
                                              Rule(id="2", direction="s2t", source="B", target="C")))
print("exact dup same target:", [c.kind for c in find_conflicts([Rule(id="1", direction="s2t", source="发", target="髮"),
                                                                    Rule(id="2", direction="s2t", source="发", target="髮")])])
# TXT roundtrip with CRLF + BOM
txt = "\ufeff软件\t軟體\r\n内存\t記憶體 內存\r\n"
res = import_rules(txt.encode("utf-8"), format="txt", direction="s2t", strict=False)
print("TXT CRLF+BOM:", [(r.source, r.target) for r in res.rules], [d.message for d in res.diagnostics])
rules = res.rules
back = import_rules(export_rules(rules, format="tsv"), format="tsv")
print("TSV roundtrip identity:", [(r.direction, r.source, r.target) for r in back.rules] == [(r.direction, r.source, r.target) for r in sorted(rules, key=lambda r: r.id)])
