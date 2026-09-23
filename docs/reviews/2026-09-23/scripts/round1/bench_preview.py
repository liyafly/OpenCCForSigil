"""Round 1 (U-04 reference): cost of one 'accept this' click in the old list preview.

Runs only against baseline b2f674b (e.g. in a `git worktree`).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)
import time

from tests.unit.test_preview_window import (
    _FakeItem,
    _FakeListWidget,
    _FakeLabel,
    _FakeButton,
    _FakeDetail,
    _FakeDialog,
)
from core.models import ConversionPlan, Diagnostic, SourceSpan, TokenChange
from core.preview import PreviewSession

try:
    from ui.preview_window import _PreviewDialog, _translator
except ImportError:
    raise SystemExit(
        "bench_preview.py measures the list-widget preview of baseline b2f674b; "
        "current code: see round2/preview_repro.py and round2/perf_model.py"
    )
from types import SimpleNamespace

_translator.set_language("en")
for N, files in ((2000, 20), (20000, 200), (50000, 500)):
    previews = []
    planned = []
    per = N // files
    for f in range(files):
        changes = tuple(
            TokenChange(
                source="汉",
                target="漢",
                span=SourceSpan(i, i + 1),
                rule_source="r",
                change_id=f"c{f}-{i}",
                file_id=f"f{f}",
                category="character",
                risk="LOW",
            )
            for i in range(per)
        )
        plan = ConversionPlan(
            source_sha256="",
            changes=changes,
            file_id=f"f{f}",
            diagnostics=tuple(
                Diagnostic(
                    "MIXED_SCRIPT",
                    "current text contains mixed simplified and traditional evidence",
                )
                for _ in range(per // 10)
            ),
        )
        previews.append(PreviewSession(plan))
        planned.append(SimpleNamespace(plan=plan))
    entries = tuple((p, c) for p in previews for c in p.changes)
    d = object.__new__(_PreviewDialog)
    d._previews = tuple(previews)
    d._entries = entries
    d._planned = planned
    d.applied = False
    d.list_widget = _FakeListWidget([_FakeItem("") for _ in entries], 5)
    d.summary = _FakeLabel()
    d.detail = _FakeDetail()
    d.dialog = _FakeDialog()
    d._qt = object()
    for n in (
        "accept_this_button",
        "reject_this_button",
        "accept_file_button",
        "reject_file_button",
        "accept_all_button",
        "reject_all_button",
        "apply_button",
        "accept_filter_button",
        "reject_filter_button",
    ):
        setattr(d, n, _FakeButton())
    t = time.perf_counter()
    for _ in range(10):
        d._accept_this()
    print(
        f"N={N}: one 'accept this' click ≈ {(time.perf_counter() - t) / 10 * 1000:.1f} ms (fake widgets, excludes Qt paint)"
    )
