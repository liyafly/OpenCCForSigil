"""D-01/D-03: time scan/plan/stage/verify on the synthetic 200-file book.

Usage: bench_plan.py [config ...]   (default: s2t s2twp)
Runs each config twice: UI defaults (classification + mixed diagnostics) and both off.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "round3"))
import _env  # noqa: F401

from book import make_book
from common import Book, request
from core.preview import PreviewSession
from core.workflow import ConversionWorkflow
from opencc_backend.backend import OpenCCBackend
from sigil.adapter import SigilBookAdapter
from sigil.scope import Scope, TargetSelection

files = make_book()
for config in sys.argv[1:] or ["s2t", "s2twp"]:
    for full in (True, False):
        book = Book(dict(files))
        backend = OpenCCBackend(config)
        workflow = ConversionWorkflow(
            SigilBookAdapter(book), backend,
            request(config, quotation_mode="corner", detailed=full, diag=full),
            targets=TargetSelection(Scope.ALL_XHTML, tuple(book.files)))
        timings = {}
        start = time.perf_counter()
        planned = workflow.plan()
        timings["plan"] = time.perf_counter() - start
        previews = [PreviewSession(item.plan) for item in planned]
        for preview in previews:
            preview.accept_all()
        start = time.perf_counter()
        staged = workflow.stage(workflow.finalize(previews))
        timings["finalize+stage"] = time.perf_counter() - start
        start = time.perf_counter()
        workflow.verify(staged)
        timings["verify"] = time.perf_counter() - start
        changes = sum(len(item.plan.changes) for item in planned)
        print(f"{config:12s} classify+diag={full!s:5s} changes={changes:7d} "
              + "  ".join(f"{k}={v:.2f}s" for k, v in timings.items()))
        backend.close()
