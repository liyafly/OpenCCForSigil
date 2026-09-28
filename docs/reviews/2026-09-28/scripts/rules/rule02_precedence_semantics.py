# ruff: noqa: E402
"""RULE-02/03/04: precedence surprises in source-stage matching."""
import os
import sys
from pathlib import Path
REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))

from rules.conflicts import find_conflicts
from rules.engine import convert_with_overlay
from rules.importers import import_rules
from rules.models import Rule, RuleSnapshot


def run(text, rules, **ctx):
    snap = RuleSnapshot.freeze(rules)
    res = convert_with_overlay(text, lambda s: s, config="s2t", snapshot=snap, **ctx)
    return res.final, [(h.rule_id, h.source, h.target) for h in res.rule_hits]


print("== RULE-02: V1 book scope beats V2 global scope at the same position ==")
v1_book = Rule(id="v1-book", type="exact", direction="s2t", source="头发", target="頭髮(书)",
               scope="book", book_fingerprint="B", semantic_version=1)
v2_global = Rule(id="v2-global", type="exact", direction="s2t", source="头发", target="頭髮(全局)",
                 scope="global", semantic_version=2, action="override", stage="source")
print("final:", run("头发", [v1_book, v2_global], book_fingerprint="B"))
print("conflicts reported:", [c.kind for c in find_conflicts([v1_book, v2_global])])

# Delimited imports use the target ruleset's semantic version (V2 by default).
tsv = "direction\tsource\ttarget\ts2t\t头发\t頭髮\n".replace("target\ts2t", "target\ns2t")
imported = import_rules(tsv, format="tsv", scope="book", book_fingerprint="B").rules
print("TSV-imported rule semantic_version:", [r.semantic_version for r in imported])

print("\n== RULE-02b: V1 profile rule loses to V1 global rule (V1 order book>global>profile) ==")
v1_profile = Rule(id="v1-profile", type="exact", direction="s2t", source="头发", target="頭髮(方案)",
                  scope="profile", profile_id="P", semantic_version=1)
v1_global = Rule(id="v1-global", type="exact", direction="s2t", source="头发", target="頭髮(全局)",
                 scope="global", semantic_version=1)
print("final:", run("头发", [v1_profile, v1_global], profile_id="P"))

print("\n== RULE-03: protect blocks the longest override; shorter override at same start is not tried ==")
protect = Rule(id="p", type="protect", direction="s2t", source="乾隆")
long_exact = Rule(id="long", type="exact", direction="s2t", source="大乾", target="大幹")
short_exact = Rule(id="short", type="exact", direction="s2t", source="大", target="太")
print("with long+short:", run("大乾隆", [protect, long_exact, short_exact]))
print("short only     :", run("大乾隆", [protect, short_exact]))

print("\n== RULE-04: leftmost match wins over scope/priority ==")
g = Rule(id="g", type="exact", direction="s2t", source="大乾", target="G", scope="global",
         semantic_version=2, action="override", stage="source")
b = Rule(id="b", type="exact", direction="s2t", source="乾隆帝", target="B", scope="book",
         book_fingerprint="B", priority=100000, semantic_version=2, action="override", stage="source")
print("global '大乾' vs book '乾隆帝'(priority 100000) on '大乾隆帝':", run("大乾隆帝", [g, b], book_fingerprint="B"))

print("\n== RULE-02c: V2 UI rule vs V1 imported correction remains distinct and blocks ==")
from ui.rules_window import review_import
ui_rule = Rule(id="ui", type="exact", direction="s2t", source="软件", target="軟體",
               semantic_version=2, action="override", stage="source")
imp = import_rules("s2t\t软件\t軟件\n", format="tsv", semantic_version=1)
rev = review_import([ui_rule], imp)
print("additions:", [(r.source, r.target, r.semantic_version) for r in rev.additions],
      "duplicates:", rev.duplicate_count, "conflicts:", [c.kind for c in rev.conflicts])
print("runtime:", "blocked before analysis" if any(c.blocking for c in rev.conflicts)
      else run("软件", [ui_rule, *rev.additions]))
