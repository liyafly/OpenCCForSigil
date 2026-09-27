"""Measure literal preview search with large synthetic change sets."""

import json
from pathlib import Path
import platform
import sys
from time import perf_counter
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / "plugin/OpenCCForSigil")]

from core.models import ConversionPlan, SourceSpan, TokenChange  # noqa: E402
from core.preview import PreviewSession  # noqa: E402
from opencc_backend import backend as backend_module  # noqa: E402
from tests.support.fake_qt import make_with_table  # noqa: E402
from ui import preview_window  # noqa: E402
from ui.i18n import Translator  # noqa: E402
from ui.preview_window import _PreviewDialog  # noqa: E402


def probe(row_count):
    changes = tuple(
        TokenChange(
            source=(f"needle token-{index}" if index == row_count // 2
                    else f"ordinary token-{index}"),
            target=f"converted-{index}", span=SourceSpan(index, index + 1),
            rule_source="OpenCC:s2t", change_id=f"change-{index}",
            file_id="chapter.xhtml", category="character", risk="LOW",
        )
        for index in range(row_count)
    )
    plan = ConversionPlan(source_sha256="", file_id="chapter.xhtml", changes=changes)
    preview = PreviewSession(plan)
    planned = (SimpleNamespace(
        source=SimpleNamespace(
            file_id="chapter.xhtml", href="Text/chapter.xhtml", document_kind="xhtml"),
        plan=plan,
    ),)
    dialog = _PreviewDialog(make_with_table(), planned, (preview,), Translator("en"))
    formatted_rows = []
    original_formatter = preview_window.format_change_row
    original_backend_init = backend_module.OpenCCBackend.__init__
    opencc_calls = []
    preview_window.format_change_row = lambda *args, **kwargs: (
        formatted_rows.append(True) or original_formatter(*args, **kwargs)
    )
    backend_module.OpenCCBackend.__init__ = lambda *args, **kwargs: (
        opencc_calls.append(True)
    )
    dialog.search_input.setText("needle")
    started = perf_counter()
    dialog._refresh()
    elapsed = perf_counter() - started
    visible = dialog._visible_entries_cache
    expected = f"change-{row_count // 2}"
    assert tuple(change.change_id for _item, change in visible) == (expected,)
    assert not formatted_rows
    assert not opencc_calls
    preview_window.format_change_row = original_formatter
    backend_module.OpenCCBackend.__init__ = original_backend_init
    dialog.dialog.reject()
    return {
        "rows": row_count,
        "matches": len(visible),
        "search_seconds": elapsed,
        "formatted_rows": len(formatted_rows),
        "opencc_calls": len(opencc_calls),
        "matcher": "casefolded literal substring",
    }


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "results": [probe(row_count) for row_count in (10_000, 300_000)],
    }
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
