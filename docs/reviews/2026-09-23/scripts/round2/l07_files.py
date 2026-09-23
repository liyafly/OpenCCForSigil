import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)
import random
import time

import rules.compiled as compiled
from core.models import ConvertRequest, RuleSnapshot as RS
from core.planner import build_conversion_plan
from document.tokenizer import tokenize_xhtml
from rules.models import Rule, RuleSnapshot
from opencc_backend.backend import OpenCCBackend

builds = [0]
ob = compiled.CompiledOverlay.build.__func__
compiled.CompiledOverlay.build = classmethod(
    lambda cls, *a, **k: (builds.__setitem__(0, builds[0] + 1), ob(cls, *a, **k))[1]
)
rng = random.Random(1)
han = [chr(c) for c in range(0x4E00, 0x4E00 + 3000)]
srcs = set()
while len(srcs) < 1976:
    srcs.add("".join(rng.choices(han, k=2)))
rules = tuple(
    Rule(id=f"r{i}", type="exact", direction="s2t", source=s, target=s[::-1])
    for i, s in enumerate(sorted(srcs))
)
backend = OpenCCBackend("s2t")
docs = []
for f in range(300):
    src = "".join("<p>%s</p>" % "".join(rng.choices(han, k=80)) for _ in range(10))
    docs.append((src, tokenize_xhtml(src)))
for label, rs in (("0 rules", ()), ("1976 rules", rules)):
    snap = RuleSnapshot.freeze(rs)
    req = ConvertRequest(
        "s2t",
        rules_snapshot=RS(rules_hash=snap.rules_hash, rules=snap.rules),
        diagnose_mixed=False,
        detailed_classification=False,
    )
    builds[0] = 0
    t = time.perf_counter()
    for i, (src, doc) in enumerate(docs):
        build_conversion_plan(
            file_id=str(i), source=src, document=doc, backend=backend, request=req
        )
    print(
        f"300 files x 10 nodes, {label}: {time.perf_counter() - t:.2f}s, overlay builds={builds[0]}"
    )
