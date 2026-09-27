#!/usr/bin/env python3
"""Measure the pure batch planner over synthetic decision-only entries."""

from __future__ import annotations

import argparse
from collections import namedtuple
import json
import platform
from pathlib import Path
import statistics
import subprocess
import sys
import time
import tracemalloc


ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "plugin/OpenCCForSigil"))

from ui.preview_batch import plan_batch_decision  # noqa: E402


BatchChange = namedtuple("BatchChange", "change_id file_id group_id")


class CountingPreview:
    plan = type("Plan", (), {"file_id": "book"})()

    def __init__(self):
        self.visits = 0

    def decision(self, change_id):
        self.visits += 1
        return "accept_this" if int(change_id.rsplit("-", 1)[1]) % 2 == 0 else None


def _plan(entries, preview):
    preview.visits = 0
    return plan_batch_decision(entries, {}, {}, scope="all", undecided_only=True)


def run_count(count: int, repeats: int) -> dict:
    preview = CountingPreview()
    entries = tuple((preview, BatchChange(f"change-{i}", "book", None))
                    for i in range(count))
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        plan = _plan(entries, preview)
        samples.append(time.perf_counter() - start)
        assert plan.change_count == count // 2
        assert preview.visits == count
        assert not any(hasattr(change, "source") for _session, change in plan.entries[:10])

    tracemalloc.start()
    memory_plan = _plan(entries, preview)
    _current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert memory_plan.change_count == count // 2 and preview.visits == count
    return {
        "input_count": count,
        "selected_count": memory_plan.change_count,
        "decision_accesses": preview.visits,
        "accesses_per_input": preview.visits / count,
        "elapsed_seconds": samples,
        "median_seconds": statistics.median(samples),
        "planner_peak_bytes_excluding_fixture": peak_bytes,
        "planner_peak_mib_excluding_fixture": round(peak_bytes / (1024 * 1024), 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--counts", default="10000,100000,300000")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    counts = tuple(int(value) for value in args.counts.split(","))
    if args.repeats < 1 or any(count <= 0 for count in counts):
        parser.error("counts and repeats must be positive")
    result = {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                        text=True).strip(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "repeats": args.repeats,
        "scope": "all, undecided_only; ungrouped synthetic entries without source/target text",
        "results": [run_count(count, args.repeats) for count in counts],
    }
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
