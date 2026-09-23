import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)
import random
import time

from core.models import ConvertRequest, RuleSnapshot as RS
from core.planner import build_conversion_plan
from document.tokenizer import tokenize_xhtml
from rules.models import Rule, RuleSnapshot
from rules.compiled import CompiledOverlay
from opencc_backend.backend import OpenCCBackend

rng = random.Random(1)
han = [chr(c) for c in range(0x4E00, 0x4E00 + 3000)]
sources = set()
while len(sources) < 1976:
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
t = time.perf_counter()
for _ in range(10):
    CompiledOverlay.build(snap, expected_hash=snap.rules_hash, config="s2t")
print("one overlay build (1976 rules): %.1f ms" % ((time.perf_counter() - t) * 100))


def run(files, nodes_per_file):
    docs = []
    for f in range(files):
        src = "".join("<p>%s</p>" % "".join(rng.choices(han, k=80)) for _ in range(nodes_per_file))
        docs.append((src, tokenize_xhtml(src)))
    t = time.perf_counter()
    for i, (src, doc) in enumerate(docs):
        build_conversion_plan(
            file_id=str(i), source=src, document=doc, backend=backend, request=req
        )
    return time.perf_counter() - t


for files, n in ((1, 3000), (30, 100), (300, 10), (1000, 3)):
    print(f"{files} files x {n} nodes: {run(files, n):.2f} s")
