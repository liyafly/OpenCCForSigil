#!/usr/bin/env python3
"""Stage timings, OpenCC call counts, and memory for a synthetic large book.

Run from the repository root:

    mise exec -- uv run python <this script> --output /tmp/opencc-pipeline.json

Only synthetic text is generated. Nothing is written to a Sigil book, the
user profile directory, logs, or history. Timings are medians of --repeats.
"""

from __future__ import annotations

import argparse
import gc
import json
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synthetic_book import (  # noqa: E402
    ROOT, CountingBackend, SyntheticBook, build_sources,
)

from core.models import ConvertRequest  # noqa: E402
from core.preview import PreviewSession  # noqa: E402
from core.staging import source_sha256  # noqa: E402
from core.workflow import ConversionWorkflow  # noqa: E402
from document.tokenizer import tokenize_xhtml  # noqa: E402
from document.validation import validate_xhtml_syntax  # noqa: E402
from opencc_backend.backend import OpenCCBackend  # noqa: E402
from sigil.adapter import SigilBookAdapter  # noqa: E402
from ui.i18n import Translator  # noqa: E402
from ui.preview_window import _diagnostic_records  # noqa: E402


def _median(fn, repeats):
    samples = []
    result = None
    for _ in range(repeats):
        gc.collect()
        start = time.perf_counter()
        result = fn()
        samples.append(time.perf_counter() - start)
    return statistics.median(samples), samples, result


def run(files, paragraphs, chars, config, repeats, detailed, diagnose):
    sources = build_sources(files, paragraphs, chars)
    report = {
        "files": files,
        "chars": sum(len(value) for value in sources.values()),
        "utf8_bytes": sum(len(value.encode("utf-8")) for value in sources.values()),
        "config": config,
        "detailed_classification": detailed,
        "diagnose_mixed": diagnose,
    }
    request = ConvertRequest(config, detailed_classification=detailed, diagnose_mixed=diagnose)

    report["tokenize_seconds"], _, _ = _median(
        lambda: [tokenize_xhtml(source) for source in sources.values()], repeats)
    report["validate_seconds"], _, _ = _median(
        lambda: [validate_xhtml_syntax(source) for source in sources.values()], repeats)

    def make_workflow():
        backend = CountingBackend(OpenCCBackend(config))
        workflow = ConversionWorkflow(
            SigilBookAdapter(SyntheticBook(sources)), backend, request)
        workflow.scan()
        return workflow

    workflows = []

    def plan_once():
        workflow = make_workflow()
        workflows.append(workflow)
        return workflow.plan()

    report["plan_seconds"], report["plan_samples"], planned = _median(plan_once, repeats)
    workflow = workflows[-1]
    backend = workflow.backend
    report["targets"] = sum(len(item.tokenized.targets) for item in planned)
    report["changes"] = sum(len(item.plan.changes) for item in planned)
    report["diagnostics"] = sum(len(item.plan.diagnostics) for item in planned)
    report["opencc_convert_calls"] = backend.convert_calls
    report["opencc_convert_chars"] = backend.convert_chars
    report["opencc_compare_calls"] = dict(backend.compare_calls)
    report["opencc_compare_chars"] = dict(backend.compare_chars)

    # Memory retained by one frozen plan set (sources are already resident).
    del workflows[:-1]
    gc.collect()
    tracemalloc.start()
    retained_workflow = make_workflow()
    before = tracemalloc.get_traced_memory()[0]
    retained_planned = retained_workflow.plan()
    after, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    report["plan_retained_mib"] = round((after - before) / 2**20, 1)
    report["plan_peak_mib"] = round((peak - before) / 2**20, 1)
    report["source_mib_utf8"] = round(report["utf8_bytes"] / 2**20, 1)
    report["targets_context_chars"] = sum(
        len(target.context) for item in retained_planned for target in item.plan.targets)
    report["targets_source_chars"] = sum(
        len(target.source_text) for item in retained_planned for target in item.plan.targets)
    del retained_workflow, retained_planned
    gc.collect()

    def previews():
        return tuple(PreviewSession(item.plan) for item in planned)

    report["preview_sessions_seconds"], _, sessions = _median(previews, repeats)
    for session in sessions:
        session.accept_all()
    report["finalize_seconds"], _, finalized = _median(
        lambda: workflow.finalize(sessions), repeats)
    report["stage_seconds"], _, staged = _median(lambda: workflow.stage(finalized), repeats)
    report["verify_seconds"], _, _ = _median(lambda: workflow.verify(staged), repeats)

    def history_manifest():
        return [{
            "before_sha256": source_sha256(item.original),
            "after_sha256": source_sha256(item.converted),
            "bytes_before": len(item.original.encode("utf-8")),
            "bytes_after": len(item.converted.encode("utf-8")),
            "high_risk_changes": sum(change.risk == "HIGH" for change in item.plan.changes),
        } for item in staged]

    report["history_manifest_seconds"], _, _ = _median(history_manifest, repeats)
    report["diagnostic_records_seconds"], _, records = _median(
        lambda: _diagnostic_records(planned, Translator("en")), repeats)
    report["diagnostic_records"] = len(records)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", type=int, default=200)
    parser.add_argument("--paragraphs", type=int, default=60)
    parser.add_argument("--chars", type=int, default=150)
    parser.add_argument("--configs", default="s2t,s2twp")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    results = []
    for config in args.configs.split(","):
        for detailed, diagnose in ((True, True), (False, False)):
            results.append(run(args.files, args.paragraphs, args.chars, config,
                               args.repeats, detailed, diagnose))
    output = {
        "head": subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                        text=True).strip(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "repeats": args.repeats,
        "results": results,
    }
    text = json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
