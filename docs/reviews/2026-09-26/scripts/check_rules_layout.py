"""Real Qt layout evidence; use --verify to enforce the review's acceptance bar.

QT_QPA_PLATFORM=offscreen PYTHONPATH=plugin/OpenCCForSigil mise exec -- \
  uv run --with PySide6==6.11.2 python \
  docs/reviews/2026-09-26/scripts/check_rules_layout.py --output /tmp/opencc-layout
"""

import argparse
import json
from pathlib import Path

import PySide6

from rules.models import Rule
from ui.i18n import Translator
from ui.qt import ensure_application, load_qt
from ui.rules_window import RuleManagerDialog


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    options = parser.parse_args()
    options.output.mkdir(parents=True, exist_ok=True)
    qt = load_qt()
    app = ensure_application(qt)
    results = []
    for language in ("en", "zh-Hans", "zh-Hant"):
        window = RuleManagerDialog(
            qt, (Rule(id="deletion", semantic_version=2, action="replace",
                      direction="s2t", source="旧词", target=""),),
            translator=Translator(language),
        )
        window.dialog.show()
        app.processEvents()
        minimum = window.dialog.minimumSizeHint()
        result = {
            "language": language,
            "minimum_width": minimum.width(),
            "minimum_height": minimum.height(),
            "initial_width": window.dialog.width(),
            "initial_height": window.dialog.height(),
            "collapsed_input_visible": window.test_input.isVisible(),
            "collapsed_input_enabled": window.test_input.isEnabled(),
            "table_height": window.table.height(),
        }
        window.dialog.grab().save(str(options.output / f"rules-{language}.png"))
        window.test_box.setChecked(True)
        app.processEvents()
        result["expanded_input_visible"] = window.test_input.isVisible()
        results.append(result)
        window.dialog.hide()
    report = {"PySide6": PySide6.__version__, "results": results}
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (options.output / "layout.json").write_text(text, encoding="utf-8")
    print(text, end="")
    if options.verify:
        for item in results:
            assert item["minimum_height"] < 600, item
            assert item["minimum_width"] <= 1000, item
            assert item["initial_height"] <= 720, item
            assert item["collapsed_input_visible"] is False, item
            assert item["expanded_input_visible"] is True, item
            assert item["table_height"] >= 150, item


if __name__ == "__main__":
    main()
