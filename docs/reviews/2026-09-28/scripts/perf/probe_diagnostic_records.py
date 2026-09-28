#!/usr/bin/env python3
"""Show that preview diagnostic records scale with diagnostics x changes per file.

`_diagnostic_records()` runs on the Qt main thread inside `_PreviewDialog`
construction. The probe counts span comparisons by wrapping the change list
and reports wall time for three per-file densities. Synthetic data only.
"""

from __future__ import annotations

import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synthetic_book import SyntheticBook, chapter  # noqa: E402

from core.models import ConvertRequest  # noqa: E402
from core.workflow import ConversionWorkflow  # noqa: E402
from opencc_backend.backend import OpenCCBackend  # noqa: E402
from sigil.adapter import SigilBookAdapter  # noqa: E402
from ui.i18n import Translator  # noqa: E402
from ui.preview_window import _diagnostic_records  # noqa: E402


def main() -> int:
    backend = OpenCCBackend("s2t")
    print("paragraphs_per_file files diagnostics changes seconds(median of 3)")
    for paragraphs in (60, 120, 240, 480):
        rng = random.Random(7)
        sources = {f"c{index}": chapter(rng, index, paragraphs, 150, inline_every=1)
                   for index in range(10)}
        workflow = ConversionWorkflow(SigilBookAdapter(SyntheticBook(sources)), backend,
                                      ConvertRequest("s2t", detailed_classification=False,
                                                     diagnose_mixed=False))
        planned = workflow.plan()
        samples = []
        for _ in range(3):
            start = time.perf_counter()
            records = _diagnostic_records(planned, Translator("en"))
            samples.append(time.perf_counter() - start)
        print(paragraphs, len(sources), len(records),
              sum(len(item.plan.changes) for item in planned),
              f"{statistics.median(samples):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
