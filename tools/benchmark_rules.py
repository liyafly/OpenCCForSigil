#!/usr/bin/env python3
"""Measure plan-scoped rule compilation across many short text targets."""

from __future__ import annotations

import argparse
from pathlib import Path
import random
import statistics
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin" / "OpenCCForSigil"))

from core.converter import OfficialBackendConverter  # noqa: E402
from core.models import ConvertRequest, RuleSnapshot as RequestRuleSnapshot  # noqa: E402
from rules.models import Rule, RuleSnapshot  # noqa: E402


class IdentityBackend:
    config = "s2t"

    def convert(self, text: str) -> str:
        return text

    def convert_for_config(self, _config: str, text: str) -> str:
        return text


def benchmark(rule_count: int, node_count: int, repeats: int) -> tuple[float, ...]:
    rules = tuple(
        Rule(id=f"bench-{index}", source=chr(0x4E00 + index) + "詞",
             target=chr(0x4E00 + index) + "語", direction="s2t")
        for index in range(rule_count)
    )
    frozen = RuleSnapshot.freeze(rules)
    request = ConvertRequest(
        "s2t",
        rules_snapshot=RequestRuleSnapshot(rules_hash=frozen.rules_hash, rules=frozen.rules),
        diagnose_mixed=False,
        detailed_classification=False,
    )
    rng = random.Random(23)
    alphabet = [chr(0x4E00 + index) for index in range(max(rule_count, 1))]
    targets = tuple("".join(rng.choices(alphabet, k=80)) for _ in range(node_count))
    timings = []
    for _ in range(repeats):
        converter = OfficialBackendConverter(IdentityBackend())
        start = perf_counter()
        for text in targets:
            converter.convert(text, request)
        timings.append(perf_counter() - start)
    return tuple(timings)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rules", type=int, default=1976)
    parser.add_argument("--nodes", type=int, default=3000)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.rules < 0 or args.nodes < 1 or args.repeats < 1:
        parser.error("--rules must be >= 0; --nodes and --repeats must be >= 1")
    timings = benchmark(args.rules, args.nodes, args.repeats)
    print(f"rules={args.rules} nodes={args.nodes} repeats={args.repeats}")
    print("seconds=" + ", ".join(f"{value:.3f}" for value in timings))
    print(f"median_seconds={statistics.median(timings):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
