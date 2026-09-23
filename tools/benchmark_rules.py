#!/usr/bin/env python3
"""Measure rule compilation through ConversionWorkflow.plan across book shapes."""

from __future__ import annotations

import argparse
from pathlib import Path
import statistics
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin" / "OpenCCForSigil"))

from core.models import ConvertRequest, RuleSnapshot as RequestRuleSnapshot  # noqa: E402
from core.workflow import ConversionWorkflow  # noqa: E402
from rules.models import Rule, RuleSnapshot  # noqa: E402
from sigil.adapter import SigilBookAdapter  # noqa: E402


class IdentityBackend:
    config = "s2t"

    def convert(self, text: str) -> str:
        return text

    def convert_for_config(self, _config: str, text: str) -> str:
        return text

    def provenance(self):
        return type("Provenance", (), {"as_dict": lambda _self: {"backend": "identity"}})()


class BenchmarkBook:
    def __init__(self, sources: dict[str, str]) -> None:
        self.sources = sources

    def text_iter(self):
        return ((file_id, f"Text/{file_id}.xhtml") for file_id in self.sources)

    def readfile(self, file_id: str) -> str:
        return self.sources[file_id]


def benchmark(rule_count: int, file_count: int, nodes_per_file: int,
              repeats: int) -> tuple[float, ...]:
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
    nodes = []
    for index in range(file_count * nodes_per_file):
        if rules:
            start = index * 40
            text = "".join(
                rules[(start + offset) % len(rules)].source for offset in range(40)
            )
            nodes.append(f"<p>{text}</p>")
        else:
            nodes.append(f"<p>{'漢字' * 40}</p>")
    sources = {
        f"chapter-{file_index}.xhtml": "".join(
            nodes[file_index * nodes_per_file:(file_index + 1) * nodes_per_file]
        )
        for file_index in range(file_count)
    }

    timings = []
    for _ in range(repeats):
        workflow = ConversionWorkflow(
            SigilBookAdapter(BenchmarkBook(sources)), IdentityBackend(), request)
        start = perf_counter()
        workflow.plan()
        timings.append(perf_counter() - start)
    return tuple(timings)


def _report(label: str, timings: tuple[float, ...], rule_count: int) -> None:
    print(f"{label}: rules={rule_count}")
    print("seconds=" + ", ".join(f"{value:.3f}" for value in timings))
    print(f"median_seconds={statistics.median(timings):.3f}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rules", type=int, default=1976)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.rules < 0 or args.repeats < 1:
        parser.error("--rules must be >= 0 and --repeats must be >= 1")

    _report("300 files x 10 nodes", benchmark(args.rules, 300, 10, args.repeats), args.rules)
    _report("1 file x 3000 nodes", benchmark(args.rules, 1, 3000, args.repeats), args.rules)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
