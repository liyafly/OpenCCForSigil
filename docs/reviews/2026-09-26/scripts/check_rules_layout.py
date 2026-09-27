"""Real Qt layout evidence; use --verify to enforce the review's acceptance bar.

QT_QPA_PLATFORM=offscreen PYTHONPATH=plugin/OpenCCForSigil mise exec -- \
  uv run --with PySide6==6.11.2 python \
  docs/reviews/2026-09-26/scripts/check_rules_layout.py --output /tmp/opencc-layout
"""

import argparse
import json
from pathlib import Path

import PySide6
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

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

    keyboard_window = RuleManagerDialog(
        qt, (), translator=Translator("en"))
    keyboard_window.dialog.show()
    app.processEvents()
    keyboard_window.source_edit.setFocus()
    QTest.keyClicks(keyboard_window.source_edit, "keyboard-source")
    QTest.keyClicks(keyboard_window.target_edit, "keyboard-target")
    QTest.keyClick(keyboard_window.target_edit, Qt.Key.Key_Return)
    app.processEvents()
    keyboard_return_applied = (
        len(keyboard_window.rules) == 1
        and keyboard_window.rules[0].source == "keyboard-source"
        and keyboard_window.rules[0].target == "keyboard-target"
        and keyboard_window._editing_rule_id is None
    )

    escape_window = RuleManagerDialog(qt, (), translator=Translator("en"))
    escape_window.dialog.show()
    app.processEvents()
    escape_window.source_edit.setText("unapplied-source")
    escape_window.target_edit.setText("unapplied-target")
    escape_window._ask_editor_draft_action = lambda: "discard"
    QTest.keyClick(escape_window.dialog, Qt.Key.Key_Escape)
    app.processEvents()
    escape_discard_closed = (
        not escape_window.dialog.isVisible() and not escape_window.rules)

    detail_rule = Rule(
        id="long-detail", source="^" + "long-source-" * 24 + "$",
        target="long-target-" * 24, direction="s2t", match_type="regex",
        semantic_version=2,
    )
    details_window = RuleManagerDialog(qt, (detail_rule,), translator=Translator("en"))
    details_window.dialog.show()
    app.processEvents()
    details_window.table.selectRow(0)
    app.processEvents()
    details_text = details_window.selection_details.toPlainText()
    full_detail_text_visible = (
        detail_rule.source in details_text and detail_rule.target in details_text)

    keyboard = {
        "return_applies_new_draft": keyboard_return_applied,
        "escape_discards_draft_and_closes": escape_discard_closed,
        "long_rule_text_available_in_details": full_detail_text_visible,
    }
    report = {"PySide6": PySide6.__version__, "results": results}
    report["keyboard_and_details"] = keyboard
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
        assert all(keyboard.values()), keyboard


if __name__ == "__main__":
    main()
