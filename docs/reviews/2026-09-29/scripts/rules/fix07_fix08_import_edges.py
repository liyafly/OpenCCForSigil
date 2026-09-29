# ruff: noqa: E401, E402, E701, E702, E731, F401, F811, F841
"""FIX-07/FIX-08: header false positives, blank direction, Unicode line separators, line numbers.

Run from the repository root. Read-only: uses temporary directories, never the user's data.
"""
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))
sys.path.insert(0, str(REPO))

from rules.importers import import_rules
from rules.exporters import export_rules, export_warnings
from rules.models import Rule

def show(tag, text, **kw):
    r = import_rules(text, strict=False, **kw)
    print(f"{tag}: rules={[(x.direction, x.source, x.target, x.comment) for x in r.rules]} diags={[(d.line, d.severity, d.message) for d in r.diagnostics]}")

print("== RULE-06 header false positives (first data row dropped silently) ==")
show("2-col list starting with 备注", "备注\t備註\n软件\t軟體\n", format="tsv", direction="s2t")
show("2-col list starting with 目标", "目标\t目標\n软件\t軟體\n", format="tsv", direction="s2t")
show("2-col list starting with 原文", "原文\t原文本\n软件\t軟體\n", format="tsv", direction="s2t")
show("en list starting with 'source'", "source\tsauce\ncolor\tcolour\n", format="tsv", direction="s2t")
show("CSV starting with 方向 row that is data", "方向,方嚮\n软件,軟體\n", format="csv", direction="s2t")
show("3-col blank-direction row (was: dialog direction)", "\t软件\t軟體\n", format="tsv", direction="s2t")

print("\n== RULE-07 TSV line splitting vs allowed characters ==")
for ch, name in (("\u2028", "U+2028"), ("\x85", "NEL U+0085"), ("\u2029", "U+2029")):
    rule = Rule(id="r", direction="s2t", source="软件", target=f"軟{ch}體")
    exported = export_rules((rule,), format="tsv")
    lossy, skipped = export_warnings((rule,), format="tsv")
    back = import_rules(exported, format="tsv", strict=False)
    print(f"{name}: export_skipped={skipped} reimported={[(x.source, x.target) for x in back.rules]} diags={[(d.line, d.message[:50]) for d in back.diagnostics]}")

print("\n== RULE-07 legacy exported TSV (csv.writer quoting) ==")
show("legacy quote-in-middle", 's2t\t"他说""好"""\t目标\t\n', format="tsv")
show("legacy multi-line quoted comment", 's2t\t软件\t軟體\t"第一行\n第二行"\ns2t\t内存\t記憶體\t\n', format="tsv")

print("\n== RULE-08 line numbers: CRLF / BOM / blank / CSV multi-line ==")
show("TSV CRLF+BOM bad row line 3", "\ufeffdirection\tsource\ttarget\r\ns2t\t软件\t軟體\r\nbad\t源\t目标\r\n", format="tsv")
show("CSV multiline record then bad row (physical line 4)", 'direction,source,target,comment\ns2t,软件,軟體,"a\nb"\nbad,源,目标,\n', format="csv")
show("CSV CRLF bad row line 3", "direction,source,target\r\ns2t,软件,軟體\r\nbad,源,目标\r\n", format="csv")
show("TSV form-feed inside comment", "s2t\t软件\t軟體\tA\x0cB\nbad\t源\t目标\n", format="tsv")
show("1-col row message prefix", "direction\tsource\ttarget\nonlyone\n", format="tsv")

print("\n== RULE-02 side effect: V2 import -> export warnings/TXT ==")
r = import_rules("软件\t軟體\n", format="tsv", direction="s2t").rules
print("imported semantic_version:", [x.semantic_version for x in r])
print("TSV export_warnings (lossy, skipped):", export_warnings(r, format="tsv"))
print("TXT export text:", repr(export_rules(r, format="txt")), "warnings:", export_warnings(r, format="txt"))
