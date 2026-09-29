# ruff: noqa: E401, E402, E701, E702, E731, F401, F811, F841
"""D9: an unrelated shorter V2 rule flips the V1 global/profile winner.

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
from rules.engine import lock_spans
from rules.models import Rule, RuleSnapshot
from rules.conflicts import find_conflicts
g1 = Rule(id="v1-global", direction="s2t", source="软件", target="軟件(全局)", semantic_version=1)
p1 = Rule(id="v1-profile", direction="s2t", source="软件", target="軟體(方案)", scope="profile",
          profile_id="P", semantic_version=1)
v2_short = Rule(id="v2-short", direction="s2t", source="软", target="軟", semantic_version=2,
                action="override", stage="source")
def win(rules, text="软件"):
    spans = lock_spans(text, RuleSnapshot.freeze(rules), config="s2t", profile_id="P")
    return [(s.rule.id, s.target) for s in spans]
print("V1 global + V1 profile           :", win((g1, p1)))
print("+ unrelated shorter V2 rule '软'  :", win((g1, p1, v2_short)))
print("conflicts reported for the trio   :", [c.kind for c in find_conflicts((g1, p1, v2_short))])
print("same trio on text '软体' (V2 only):", win((g1, p1, v2_short), "软体"))
