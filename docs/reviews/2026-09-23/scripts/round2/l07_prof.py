import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)
import random
import time
import cProfile
import pstats

from core.models import ConvertRequest, RuleSnapshot as RS
from core.planner import build_conversion_plan
from document.tokenizer import tokenize_xhtml
from rules.models import Rule, RuleSnapshot
from opencc_backend.backend import OpenCCBackend

rng = random.Random(1)
han = [chr(c) for c in range(0x4E00, 0x4E00 + 3000)]
nrules = int(sys.argv[1])
sources = set()
while len(sources) < nrules:
    sources.add("".join(rng.choices(han, k=2)))
rules = tuple(
    Rule(id=f"r{i}", type="exact", direction="s2t", source=s, target=s[::-1])
    for i, s in enumerate(sorted(sources))
)
snap = RuleSnapshot.freeze(rules)
req = ConvertRequest(
    "s2t",
    rules_snapshot=RS(rules_hash=snap.rules_hash, rules=snap.rules),
    diagnose_mixed=False,
    detailed_classification=False,
)
backend = OpenCCBackend("s2t")
src = "".join("<p>%s</p>" % "".join(rng.choices(han, k=80)) for _ in range(3000))
doc = tokenize_xhtml(src)
pr = cProfile.Profile()
pr.enable()
t = time.perf_counter()
plan = build_conversion_plan(file_id="x", source=src, document=doc, backend=backend, request=req)
print("elapsed", time.perf_counter() - t, "changes", len(plan.changes))
pr.disable()
pstats.Stats(pr).sort_stats("tottime").print_stats(6)
