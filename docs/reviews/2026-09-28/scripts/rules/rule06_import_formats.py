# ruff: noqa: E402
"""RULE-06/07/08: TSV/CSV/JSON import surprises."""
import os
import sys
from pathlib import Path
REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))

from rules.exporters import export_rules
from rules.importers import import_rules
from rules.models import Rule, canonical_rule_dict


def show(label, text, **kw):
    try:
        res = import_rules(text, strict=False, **kw)
        print(label, "rules=", [(r.direction, r.source, r.target) for r in res.rules],
              "diagnostics=", [(d.line, d.location, d.message) for d in res.diagnostics])
    except Exception as exc:
        print(label, type(exc).__name__, exc)


print("== RULE-06: simplest 2-column TSV '源<TAB>目标' is rejected even with a direction chosen ==")
show("2-col TSV:", "软件\t軟體\n内存\t記憶體\n", format="tsv", direction="s2t")
show("3-col TSV without direction column (源/目标/备注):", "软件\t軟體\t台湾用语\n", format="tsv", direction="s2t")
show("Chinese header row:", "方向\t源文本\t目标文本\ns2t\t软件\t軟體\n", format="tsv", direction="s2t")

print("\n== RULE-07: TSV goes through csv quoting: ASCII quotes are eaten / swallow lines ==")
show("quoted source :", 's2t\t"引号"\t「引号」\n', format="tsv")
show("unbalanced quote:", 's2t\t"开头\t「开头\ns2t\t软件\t軟體\ns2t\t内存\t記憶體\n', format="tsv")

print("\n== RULE-08: delimited error line numbers are record indexes, not file lines ==")
tsv = "direction\tsource\ttarget\n\n\ns2t\t软件\t軟體\n\ns2x\t内存\t記憶體\n"
show("bad direction on physical line 6:", tsv, format="tsv")

print("\n== RULE-09: JSON import ignores the scope chosen in the import dialog ==")
exported = export_rules([Rule(id="g1", type="exact", direction="s2t", source="软件", target="軟體")], format="json")
res = import_rules(exported, format="json", scope="book", book_fingerprint="THIS-BOOK", profile_id="P")
r = res.rules[0]
print("chosen scope=book -> imported scope:", r.scope, "book_fingerprint:", repr(r.book_fingerprint),
      "profile_id:", repr(r.profile_id))
foreign = export_rules([Rule(id="f1", type="exact", direction="s2t", source="软件", target="軟體",
                             scope="book", book_fingerprint="OTHER-BOOK")], format="json")
r = import_rules(foreign, format="json", scope="book", book_fingerprint="THIS-BOOK").rules[0]
print("foreign book rule -> scope:", r.scope, "owner:", r.book_fingerprint, "(never active in this book)")

print("\n== JSON roundtrip identity (global rule, current profile P) ==")
orig = Rule(id="g2", type="exact", direction="s2t", source="软件", target="軟體")
back = import_rules(export_rules([orig], format="json"), format="json", profile_id="P").rules[0]
print("canonical equal:", canonical_rule_dict(orig) == canonical_rule_dict(back),
      "diff:", {k: (canonical_rule_dict(orig)[k], v) for k, v in canonical_rule_dict(back).items()
                if canonical_rule_dict(orig).get(k) != v})
