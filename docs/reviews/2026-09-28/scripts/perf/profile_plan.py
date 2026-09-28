"""cProfile one full ConversionWorkflow.plan() over the synthetic book."""

from __future__ import annotations

import argparse
import cProfile
import pstats
import time

from synthetic_book import CountingBackend, SyntheticBook, build_sources  # noqa: E402

from core.models import ConvertRequest  # noqa: E402
from core.workflow import ConversionWorkflow  # noqa: E402
from opencc_backend.backend import OpenCCBackend  # noqa: E402
from sigil.adapter import SigilBookAdapter  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", type=int, default=200)
    parser.add_argument("--paragraphs", type=int, default=60)
    parser.add_argument("--chars", type=int, default=150)
    parser.add_argument("--config", default="s2t")
    parser.add_argument("--fast", action="store_true",
                        help="disable detailed_classification and diagnose_mixed")
    parser.add_argument("--top", type=int, default=35)
    args = parser.parse_args()
    sources = build_sources(args.files, args.paragraphs, args.chars)
    total = sum(len(s) for s in sources.values())
    print(f"files={len(sources)} chars={total} utf8_bytes={sum(len(s.encode()) for s in sources.values())}")
    backend = CountingBackend(OpenCCBackend(args.config))
    request = ConvertRequest(args.config, detailed_classification=not args.fast,
                             diagnose_mixed=not args.fast)
    workflow = ConversionWorkflow(SigilBookAdapter(SyntheticBook(sources)), backend, request)
    workflow.scan()
    profiler = cProfile.Profile()
    start = time.perf_counter()
    profiler.enable()
    planned = workflow.plan()
    profiler.disable()
    elapsed = time.perf_counter() - start
    print(f"plan_seconds(profiled)={elapsed:.3f} changes={sum(len(p.plan.changes) for p in planned)} "
          f"targets={sum(len(p.tokenized.targets) for p in planned)} "
          f"diagnostics={sum(len(p.plan.diagnostics) for p in planned)}")
    print(f"convert_calls={backend.convert_calls} convert_chars={backend.convert_chars} "
          f"compare_calls={backend.compare_calls} compare_chars={backend.compare_chars}")
    stats = pstats.Stats(profiler)
    stats.sort_stats("tottime").print_stats(args.top)


if __name__ == "__main__":
    main()
