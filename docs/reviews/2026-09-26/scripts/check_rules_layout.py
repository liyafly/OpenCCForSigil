"""Real Qt layout evidence; use --verify to enforce the review's acceptance bar.

QT_QPA_PLATFORM=offscreen PYTHONPATH=plugin/OpenCCForSigil mise exec -- \
  uv run --with PySide6==6.11.2 python \
  docs/reviews/2026-09-26/scripts/check_rules_layout.py --output /tmp/opencc-layout
"""

import argparse
import json
import os
import platform
from pathlib import Path
import subprocess
import sys

import PySide6
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from rules.exporters import export_rules
from rules.models import Rule
from ui.i18n import Translator
from ui.qt import ensure_application, load_qt
from ui.rules_window import RuleManagerDialog


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=640)
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
            official_convert=lambda _config, value: value,
        )
        window.dialog.resize(1000, 640)
        app.processEvents()
        window.dialog.resize(960, 640)
        app.processEvents()
        window.dialog.resize(options.width, options.height)
        window.dialog.show()
        app.processEvents()
        window.tabs.setCurrentIndex(0)
        window.editor_splitter.setSizes([300, 500])
        app.processEvents()
        before_sizes = window.editor_splitter.sizes()
        before_ratio = before_sizes[0] / max(sum(before_sizes), 1)
        # A same-orientation resize must preserve the user's divider choice.
        resize_width = options.width + (10 if options.width < 990 else -10)
        window.dialog.resize(resize_width, options.height + 10)
        app.processEvents()
        after_sizes = window.editor_splitter.sizes()
        after_ratio = after_sizes[0] / max(sum(after_sizes), 1)
        resize_preserves_split_ratio = abs(before_ratio - after_ratio) <= 0.08
        window.dialog.resize(options.width, options.height)
        app.processEvents()
        minimum = window.dialog.minimumSizeHint()
        result = {
            "language": language,
            "minimum_width": minimum.width(),
            "minimum_height": minimum.height(),
            "initial_width": window.dialog.width(),
            "initial_height": window.dialog.height(),
            "editor_source_visible": window.source_edit.isVisible(),
            "editor_target_visible": window.target_edit.isVisible(),
            "bottom_actions_visible": (window.apply_button.isVisible()
                                        and window.cancel_button.isVisible()),
            "editor_label_count_after_resize": len(
                window.editor_panel.findChildren(qt.QLabel)),
            "table_height": window.table.height(),
            "same_orientation_resize_preserves_split_ratio": resize_preserves_split_ratio,
            "split_ratio_before_resize": before_ratio,
            "split_ratio_after_resize": after_ratio,
        }
        window.dialog.grab().save(str(options.output / f"rules-{language}.png"))
        window.tabs.setCurrentIndex(1)
        app.processEvents()
        result["test_input_visible"] = window.test_input.isVisible()
        result["test_output_visible"] = window.test_output.isVisible()
        window.test_input.setPlainText("test before")
        window._test()
        result["sandbox_test_ran"] = bool(window.test_output.toPlainText())
        result["fresh_result_not_marked_stale"] = not window.test_result_status.isVisible()
        window.test_input.setPlainText("test after")
        result["input_change_marks_stale"] = window.test_result_status.isVisible()
        window._mark_test_result_current()
        window.test_scope_combo.setCurrentIndex(
            window.test_scope_combo.findData("run"))
        result["scope_change_marks_stale"] = window.test_result_status.isVisible()
        window._mark_test_result_current()
        if window.direction_combo.count() > 1:
            next_direction = (0 if window.direction_combo.currentIndex() != 0 else 1)
            window.direction_combo.setCurrentIndex(next_direction)
        result["rule_direction_change_marks_stale"] = window.test_result_status.isVisible()
        window._mark_test_result_current()
        window.source_edit.setText("working copy source")
        window.target_edit.setText("working copy target")
        window._mark_test_result_current()
        window._add()
        result["working_copy_add_marks_stale"] = (
            window.test_result_status.isVisible()
            and any(rule.source == "working copy source" for rule in window.rules))
        added_row = next(index for index, rule in enumerate(window.rules)
                         if rule.source == "working copy source")
        window.table.selectRow(added_row)
        app.processEvents()
        window._mark_test_result_current()
        window.target_edit.setText("updated working copy target")
        window._update_selected()
        result["working_copy_update_marks_stale"] = (
            window.test_result_status.isVisible()
            and any(rule.target == "updated working copy target" for rule in window.rules))
        added_row = next(index for index, rule in enumerate(window.rules)
                         if rule.source == "working copy source")
        window.table.selectRow(added_row)
        app.processEvents()
        window._mark_test_result_current()
        window._remove()
        result["working_copy_remove_marks_stale"] = (
            window.test_result_status.isVisible()
            and not any(rule.source == "working copy source" for rule in window.rules))
        window.dialog.grab().save(str(options.output / f"rules-test-{language}.png"))
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
    template_window = RuleManagerDialog(qt, (), translator=Translator("en"))
    template_window.dialog.show()
    template_window.tabs.setCurrentIndex(1)
    app.processEvents()
    template_window._mark_test_result_current()
    original_input_dialog = getattr(qt, "QInputDialog", None)
    qt.QInputDialog = type("InputDialog", (), {
        "getItem": staticmethod(lambda *_args: (
            template_window._labels["template_signature"], True)),
    })
    template_window._fill_template()
    keyboard["template_fill_marks_test_result_stale"] = (
        template_window.test_result_status.isVisible()
        and not template_window.rules
        and bool(template_window.source_edit.text()))
    if original_input_dialog is None:
        del qt.QInputDialog
    else:
        qt.QInputDialog = original_input_dialog

    import_window = RuleManagerDialog(qt, (), translator=Translator("en"))
    import_window.dialog.show()
    import_window.tabs.setCurrentIndex(1)
    app.processEvents()
    imported_file = options.output / "stale-import.json"
    imported_file.write_text(export_rules((Rule(
        id="qt-imported", source="imported source", target="imported target",
        direction="s2t"),)), encoding="utf-8")
    original_file_dialog = qt.QFileDialog
    qt.QFileDialog = type("FileDialog", (), {
        "getOpenFileName": staticmethod(lambda *_args: (str(imported_file), "")),
    })
    import_window._import_options = lambda _path: {
        "format": "json", "direction": "s2t", "scope": "global", "strict": True,
    }
    import_window._confirm_import = lambda _review: True
    import_window._mark_test_result_current()
    import_window._import()
    keyboard["import_accept_marks_test_result_stale"] = (
        import_window.test_result_status.isVisible()
        and any(rule.source == "imported source" for rule in import_window.rules))
    qt.QFileDialog = original_file_dialog
    navigation_window = RuleManagerDialog(qt, (), translator=Translator("en"))
    navigation_window.source_edit.setText("unapplied source")
    navigation_window.target_edit.setText("unapplied target")
    navigation_window.tabs.setCurrentIndex(1)
    app.processEvents()
    navigation_window.tabs.setCurrentIndex(0)
    app.processEvents()
    keyboard["tab_switch_keeps_rule_draft_unapplied"] = (
        navigation_window.source_edit.text() == "unapplied source"
        and navigation_window.target_edit.text() == "unapplied target"
        and not navigation_window.rules
    )
    return_window = RuleManagerDialog(
        qt, (), translator=Translator("en"),
        official_convert=lambda _config, value: value)
    return_window.test_input.setPlainText("keep test input")
    return_window.source_edit.setText("draft source")
    return_window.target_edit.setText("draft target")
    return_window._ask_editor_draft_action = lambda: None
    return_window._test()
    keyboard["test_return_preserves_input_and_draft"] = (
        return_window.test_input.toPlainText() == "keep test input"
        and return_window.source_edit.text() == "draft source"
        and not return_window.rules
    )

    apply_window = RuleManagerDialog(
        qt, (), translator=Translator("en"),
        official_convert=lambda _config, value: value)
    apply_window.test_input.setPlainText("input")
    apply_window.source_edit.setText("draft source")
    apply_window.target_edit.setText("draft target")
    apply_window._ask_editor_draft_action = lambda: "apply"
    apply_window._test()
    keyboard["test_apply_adds_rule_to_working_copy"] = any(
        rule.source == "draft source" and rule.target == "draft target"
        for rule in apply_window.rules)

    discard_window = RuleManagerDialog(
        qt, (), translator=Translator("en"),
        official_convert=lambda _config, value: value)
    discard_window.test_input.setPlainText("input")
    discard_window.source_edit.setText("discarded source")
    discard_window.target_edit.setText("discarded target")
    discard_window._ask_editor_draft_action = lambda: "discard"
    discard_window._test()
    keyboard["test_discard_does_not_add_rule"] = not discard_window.rules

    conflicted = RuleManagerDialog(qt, (
        Rule(id="conflict-a", source="same", target="first", direction="s2t"),
        Rule(id="conflict-b", source="same", target="second", direction="s2t"),
    ), translator=Translator("en"))
    conflicted.search_edit.setText("does-not-match")
    app.processEvents()
    conflict_item = conflicted.conflict_list.item(0)
    conflicted._select_conflict_item(conflict_item)
    keyboard["conflict_jump_clears_filter_and_selects_rule_id"] = (
        conflicted._visible_rule_ids == ["conflict-a", "conflict-b"]
        and conflicted._editing_rule_id in {"conflict-a", "conflict-b"}
        and "1" in conflicted.conflicts_label.text()
    )
    screen = app.primaryScreen()
    report = {
        "PySide6": PySide6.__version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "qpa_platform": os.environ.get("QT_QPA_PLATFORM"),
        "screen_geometry": ([screen.geometry().width(), screen.geometry().height()]
                            if screen else None),
        "screen_device_pixel_ratio": screen.devicePixelRatio() if screen else None,
        "git_head": subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True,
            text=True).stdout.strip(),
        "results": results,
    }
    report["keyboard_and_details"] = keyboard
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (options.output / "layout.json").write_text(text, encoding="utf-8")
    print(text, end="")
    if options.verify:
        for item in results:
            assert item["minimum_height"] <= 640, item
            assert item["minimum_width"] <= 1000, item
            assert item["initial_height"] <= 800, item
            assert item["editor_source_visible"] is True, item
            assert item["editor_target_visible"] is True, item
            assert item["bottom_actions_visible"] is True, item
            assert item["editor_label_count_after_resize"] == 10, item
            assert item["same_orientation_resize_preserves_split_ratio"] is True, item
            assert item["test_input_visible"] is True, item
            assert item["test_output_visible"] is True, item
            assert item["sandbox_test_ran"] is True, item
            assert item["fresh_result_not_marked_stale"] is True, item
            assert item["input_change_marks_stale"] is True, item
            assert item["scope_change_marks_stale"] is True, item
            assert item["rule_direction_change_marks_stale"] is True, item
            assert item["working_copy_add_marks_stale"] is True, item
            assert item["working_copy_update_marks_stale"] is True, item
            assert item["working_copy_remove_marks_stale"] is True, item
            assert item["table_height"] >= 100, item
        assert all(keyboard.values()), keyboard


if __name__ == "__main__":
    main()
