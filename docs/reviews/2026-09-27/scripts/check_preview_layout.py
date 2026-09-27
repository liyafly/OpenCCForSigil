"""Measure real Qt preview geometry; optional acceptance checks for Luna."""

import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "plugin/OpenCCForSigil"))

import PySide6  # noqa: E402
from core.models import ConversionPlan, SourceSpan, TokenChange  # noqa: E402
from core.preview import PreviewSession  # noqa: E402
from ui.i18n import Translator  # noqa: E402
from ui.preview_window import _PreviewDialog  # noqa: E402
from ui.qt import ensure_application, load_qt  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    qt = load_qt()
    app = ensure_application(qt)
    change = TokenChange(
        source="软件", target="軟體", span=SourceSpan(0, 2),
        rule_source="UserRule:example", change_id="change-0", file_id="chapter",
        group_id="rules:example", category="user_rule", risk="HIGH",
    )
    plan = ConversionPlan(source_sha256="", file_id="chapter", changes=(change,))
    planned = (SimpleNamespace(
        source=SimpleNamespace(file_id="chapter", href="Text/chapter.xhtml",
                               document_kind="xhtml"), plan=plan),)
    results = []
    for language in ("en", "zh-Hans", "zh-Hant"):
        window = _PreviewDialog(qt, planned, (PreviewSession(plan),), Translator(language))
        window.dialog.show()
        app.processEvents()
        minimum = window.dialog.minimumSizeHint()
        item = {
            "language": language,
            "minimum_width": minimum.width(), "minimum_height": minimum.height(),
            "initial_width": window.dialog.width(), "initial_height": window.dialog.height(),
            "table_height": window.table_view.height(),
        }
        window.dialog.grab().save(str(args.output / f"preview-{language}.png"))
        results.append(item)
        window.dialog.hide()
    report = {"PySide6": PySide6.__version__, "results": results}
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (args.output / "layout.json").write_text(text, encoding="utf-8")
    print(text, end="")
    if args.verify:
        for item in results:
            assert item["minimum_width"] <= 1000, item
            assert item["minimum_height"] < 600, item
            assert item["initial_width"] <= 1200, item
            assert item["initial_height"] <= 720, item
            assert item["table_height"] >= 150, item


if __name__ == "__main__":
    main()
