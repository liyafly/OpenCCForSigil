# ruff: noqa: E402
"""RULE-05: conflicts between two rulesets of the same run are invisible in the manager."""
import os
import sys
from pathlib import Path
REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))

from rules.compiled import CompiledOverlay
from rules.conflicts import find_conflicts, BlockingRuleConflict
from rules.models import Rule, RuleSnapshot

a = Rule(id="a1", type="exact", direction="s2t", source="软件", target="軟體")      # ruleset "taiwan-terms"
b = Rule(id="b1", type="exact", direction="s2t", source="软件", target="軟件")      # ruleset "default"
# RuleManagerDialog._refresh() only runs find_conflicts(self.rules) for the ruleset on screen:
print("conflicts shown while editing set A:", [c.kind for c in find_conflicts([a])])
print("conflicts shown while editing set B:", [c.kind for c in find_conflicts([b])])
# RunSettings.freeze_rules() concatenates every enabled referenced ruleset; planning then does:
snap = RuleSnapshot.freeze([a, b])
try:
    CompiledOverlay.build(snap, config="s2t")
    print("analysis: OK")
except BlockingRuleConflict as exc:
    print("analysis:", type(exc).__name__, "->", exc)

print("\n-- Spec §83 example: global vs profile rule for the same source (shadowing) --")
g = Rule(id="g", type="exact", direction="s2twp", source="服务器", target="伺服器", scope="global",
         semantic_version=2, action="override", stage="source")
p = Rule(id="p", type="exact", direction="s2twp", source="服务器", target="服務器", scope="profile",
         profile_id="P", priority=200, semantic_version=2, action="override", stage="source")
print("find_conflicts -> ", find_conflicts([g, p]), "(spec §83 wants the pair listed with 'Winner: profile rule')")
protect = Rule(id="keep", type="protect", direction="s2twp", source="服务器")
print("protect + exact with identical source -> ", find_conflicts([protect, g]),
      "(the exact rule can never apply; nothing tells the user)")
