#!/usr/bin/env python3
"""Real-Qt cost of the eager QTableWidget diagnostics panel.

    QT_QPA_PLATFORM=offscreen mise exec -- uv run --with PySide6==6.11.2 python <script>

Builds synthetic `_DiagnosticRecord`s (no book text) and measures panel
construction (collapsed, as in the preview dialog) and one file-filter change.
"""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import synthetic_book  # noqa: E402,F401

from ui import preview_window as pw  # noqa: E402
from ui.i18n import Translator  # noqa: E402
from ui.qt import ensure_application, load_qt  # noqa: E402


def main() -> int:
    qt = load_qt()
    app = ensure_application(qt, language="en")
    translator = Translator("en")
    print("records construct_s filter_change_s clear_filter_s")
    for count in (1_000, 10_000, 50_000):
        records = tuple(pw._DiagnosticRecord(
            file_id=f"f{index % 200}", href=f"Text/f{index % 200}.xhtml",
            code="INLINE_BOUNDARY", name="Inline boundary", description="desc",
            location=f"Line {index}, column 1", excerpt="…", related_changes=())
            for index in range(count))
        samples = []
        for _ in range(3):
            start = time.perf_counter()
            panel = pw._DiagnosticPanel(qt, records, translator)
            app.processEvents()
            samples.append(time.perf_counter() - start)
        start = time.perf_counter()
        panel.file_filter.setCurrentIndex(1)
        app.processEvents()
        filtered = time.perf_counter() - start
        start = time.perf_counter()
        panel.file_filter.setCurrentIndex(0)
        app.processEvents()
        cleared = time.perf_counter() - start
        print(count, f"{statistics.median(samples):.3f}", f"{filtered:.3f}", f"{cleared:.3f}")
        panel.widget.deleteLater()
        app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
