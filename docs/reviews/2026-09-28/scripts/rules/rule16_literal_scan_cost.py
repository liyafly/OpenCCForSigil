# ruff: noqa: E402
"""RULE-16: literal matching scans every rule per text target; CompiledOverlay.index is never used."""
import os
import random
import sys
import time
from pathlib import Path
REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))
from rules.compiled import CompiledOverlay, lock_spans_compiled
from rules.models import Rule, RuleSnapshot

random.seed(7)
han = [chr(c) for c in range(0x4E00, 0x4E00 + 3000)]
paragraphs = ["".join(random.choice(han) for _ in range(100)) for _ in range(3000)]  # ~300k chars book
for n in (100, 1000, 5000):
    rules = [Rule(id=f"r{i:05d}", direction="s2t", source="".join(random.choice(han) for _ in range(3)),
                  target="X") for i in range(n)]
    overlay = CompiledOverlay.build(RuleSnapshot.freeze(rules), config="s2t")
    start = time.perf_counter()
    hits = sum(len(lock_spans_compiled(p, overlay)) for p in paragraphs)
    print(f"{n:5d} literal rules x 3000 paragraphs: {time.perf_counter() - start:6.2f}s  hits={hits}"
          f"  index buckets built={len(overlay.index)} (unused)")
