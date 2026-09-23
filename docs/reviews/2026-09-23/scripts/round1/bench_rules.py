"""Round 1 (L-07): rule-overlay cost versus rule count, one converter.

Baseline b2f674b: about 36.5 s estimated for 3000 nodes with ~2000 rules.
Note: this reuses one converter, so it does not show the per-file rebuild
found in round 2 (see ../round2/l07_files.py).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)

import random
import time

from core.converter import OfficialBackendConverter
from core.models import ConvertRequest, RuleSnapshot as CoreSnapshot
from opencc_backend.backend import OpenCCBackend
from rules.models import Rule, RuleSnapshot

CHARS = (
    "的一是在不了有和人这中大为上个国我以要他时来用们生到作地于出就分对成会可主发年动同工也能下过子说产种面"
    "而方后多定行学法所民得经十三之进着等部度家电力里如水化高自二理起小物现实加量都两体制机当使点从业本去把性"
    "好应开它合还因由其些然前外天政四日那社义事平形相全表间样与关各重新线内数正心反你明看原又么利比或但质气第"
    "向道命此变条只没结解问意建月公无系军很情者最立代想已通并提直题党程展五果料象员革位入常文总次品式活设及管"
    "特件长求老头基资边流路级少图山统接知较将组见计别她手角期根论运农指几九区强放决西被干做必战先回则任取据处理府研"
)


def make_nodes(rng, count=3000, length=80):
    return ["".join(rng.choice(CHARS) for _ in range(length)) for _ in range(count)]


def make_request(rng, rule_count):
    rules, seen = [], set()
    for index in range(rule_count):
        source = "".join(rng.choice(CHARS) for _ in range(2))
        if source in seen:
            continue  # avoid blocking same-source conflicts
        seen.add(source)
        rules.append(Rule(id=f"r{index}", type="exact", direction="s2t", source=source, target="X"))
    snapshot = RuleSnapshot.freeze(rules)
    request = ConvertRequest(
        "s2t",
        rules_snapshot=CoreSnapshot(rules_hash=snapshot.sha256, rules=snapshot.rules),
        detailed_classification=False,
        diagnose_mixed=False,
    )
    return request, len(rules)


if __name__ == "__main__":
    rng = random.Random(1)
    converter = OfficialBackendConverter(OpenCCBackend("s2t"))
    nodes = make_nodes(rng)
    for rule_count in (0, 50, 500, 2000):
        request, unique = make_request(rng, rule_count)
        start = time.perf_counter()
        for node in nodes[:300]:
            converter.convert(node, request)
        elapsed = time.perf_counter() - start
        print(f"rules={unique}: 300 nodes {elapsed:.3f}s -> est 3000 nodes {elapsed * 10:.1f}s")
