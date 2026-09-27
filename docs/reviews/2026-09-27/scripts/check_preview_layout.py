"""Measure real Qt preview geometry; optional acceptance checks for Luna."""

import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "plugin/OpenCCForSigil"))

import PySide6  # noqa: E402
from PySide6.QtCore import QEventLoop, Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402
from core.models import ConversionPlan, SourceSpan, TokenChange  # noqa: E402
from core.preview import PreviewSession  # noqa: E402
from ui.i18n import Translator  # noqa: E402
from ui.preview_window import _PreviewDialog  # noqa: E402
from ui.qt import ensure_application, load_qt  # noqa: E402


def exercise_group_actions(qt, app, language):
    translator = Translator(language)
    language_changes = (
        TokenChange(
            source="zh-CN", target="zh-TW", span=SourceSpan(0, 5),
            rule_source="language_metadata", change_id="language-chapter",
            file_id="chapter", category="language_metadata", risk="HIGH",
            group_id="language_metadata",
        ),
        TokenChange(
            source="zh-CN", target="zh-TW", span=SourceSpan(0, 5),
            rule_source="language_metadata", change_id="language-opf",
            file_id="content.opf", category="language_metadata", risk="HIGH",
            group_id="language_metadata",
        ),
    )
    rule_changes = tuple(
        TokenChange(
            source="软件", target="軟體", span=SourceSpan(index * 2, index * 2 + 2),
            rule_source="UserRule:example", change_id=f"rule-{index}",
            file_id="chapter", category="user_rule", risk="HIGH",
            group_id="rules:occurrence-1",
        )
        for index in range(2)
    )
    chapter_plan = ConversionPlan(
        source_sha256="", file_id="chapter", changes=(language_changes[0], *rule_changes))
    opf_plan = ConversionPlan(
        source_sha256="", file_id="content.opf", changes=(language_changes[1],))
    planned = tuple(SimpleNamespace(
        source=SimpleNamespace(file_id=file_id, href=href, document_kind=kind), plan=plan,
    ) for file_id, href, kind, plan in (
        ("chapter", "Text/chapter.xhtml", "xhtml", chapter_plan),
        ("content.opf", "content.opf", "metadata", opf_plan),
    ))
    previews = (PreviewSession(chapter_plan), PreviewSession(opf_plan))
    dialog = _PreviewDialog(qt, planned, previews, translator)
    dialog.dialog.show()
    dialog.dialog.activateWindow()
    dialog.dialog.raise_()
    app.processEvents()
    assert dialog.accept_group_button.isVisible()
    group_label = dialog.accept_group_button.text()
    dialog.accept_group_button.click()
    app.processEvents()
    assert all(previews[index].decision(change.change_id).value == "accept_this"
               for index, change in enumerate((language_changes[0], language_changes[1])))
    assert all(previews[0].decision(change.change_id) is None for change in rule_changes)
    dialog.accept_file_button.click()
    app.processEvents()
    assert all(previews[0].decision(change.change_id).value == "accept_this"
               for change in rule_changes)
    dialog.dialog.hide()

    rule_plan = ConversionPlan(source_sha256="", file_id="chapter", changes=rule_changes)
    rule_only = _PreviewDialog(
        qt,
        (SimpleNamespace(
            source=SimpleNamespace(file_id="chapter", href="Text/chapter.xhtml",
                                   document_kind="xhtml"), plan=rule_plan,
        ),),
        (PreviewSession(rule_plan),), translator,
    )
    rule_only.dialog.show()
    app.processEvents()
    assert not rule_only.accept_group_button.isVisible()
    rule_only.accept_group_button.click()
    app.processEvents()
    assert all(rule_only._previews[0].decision(change.change_id) is None
               for change in rule_changes)
    rule_only.accept_file_button.click()
    app.processEvents()
    assert all(rule_only._previews[0].decision(change.change_id).value == "accept_this"
               for change in rule_changes)
    rule_only._set_current_row(0)
    assert rule_only.reset_current_button.isEnabled()
    rule_only.reset_current_button.click()
    app.processEvents()
    assert all(rule_only._previews[0].decision(change.change_id) is None
               for change in rule_changes)
    rule_only.undo_button.click()
    app.processEvents()
    assert all(rule_only._previews[0].decision(change.change_id).value == "accept_this"
               for change in rule_changes)
    rule_only.dialog.hide()

    filtered_previews = (PreviewSession(
        ConversionPlan(source_sha256="", file_id=file_id, changes=(change,)))
        for file_id, change in zip(("chapter", "content.opf"), language_changes)
    )
    filtered_previews = tuple(filtered_previews)
    filtered_plans = tuple(SimpleNamespace(
        source=SimpleNamespace(file_id=file_id, href=href, document_kind=kind),
        plan=preview.plan,
    ) for file_id, href, kind, preview in zip(
        ("chapter", "content.opf"), ("Text/chapter.xhtml", "content.opf"),
        ("xhtml", "metadata"), filtered_previews,
    ))
    filtered = _PreviewDialog(qt, filtered_plans, filtered_previews, translator)
    filtered.file_filter.setCurrentIndex(filtered.file_filter.findData("chapter"))
    filtered._refresh()
    filtered.dialog.show()
    app.processEvents()

    def click_modal(index):
        modal = app.activeModalWidget()
        assert isinstance(modal, QMessageBox), modal
        modal.buttons()[index].click()

    QTimer.singleShot(0, lambda: click_modal(1))
    filtered._decide_filtered(True)
    app.processEvents()
    assert all(preview.decision(preview.changes[0].change_id) is None
               for preview in filtered_previews)
    QTimer.singleShot(0, lambda: click_modal(0))
    filtered._decide_filtered(True)
    app.processEvents()
    assert all(preview.decision(preview.changes[0].change_id).value == "accept_this"
               for preview in filtered_previews)
    filtered.dialog.hide()
    return {
        "language_group_label": group_label,
        "language_group_accepts_both_files": True,
        "language_button_leaves_rule_group_pending": True,
        "accept_file_completes_local_rule_group": True,
        "rule_only_language_button_hidden_and_inert": True,
        "hidden_group_prompt_cancel_preserves_and_confirm_expands": True,
    }


def exercise_filters(qt, app, language, output_dir):
    translator = Translator(language)
    changes = (
        TokenChange(
            source="needle 源", target="目标甲", span=SourceSpan(0, 7),
            rule_source="UserRule:alpha", change_id="filter-1", file_id="chapter",
            category="user_rule", risk="LOW",
        ),
        TokenChange(
            source="普通文本", target="needle target", span=SourceSpan(0, 4),
            rule_source="UserRule:alpha", change_id="filter-2", file_id="chapter",
            category="user_rule", risk="LOW",
        ),
        TokenChange(
            source="needle other", target="other target", span=SourceSpan(0, 5),
            rule_source="UserRule:beta", change_id="filter-3", file_id="other",
            category="user_rule", risk="LOW",
        ),
    )
    chapter_plan = ConversionPlan(
        source_sha256="", file_id="chapter", changes=changes[:2])
    other_plan = ConversionPlan(source_sha256="", file_id="other", changes=(changes[2],))
    planned = tuple(SimpleNamespace(
        source=SimpleNamespace(file_id=file_id, href=href, document_kind="xhtml"),
        plan=plan,
    ) for file_id, href, plan in (
        ("chapter", "Text/chapter.xhtml", chapter_plan),
        ("other", "Text/other.xhtml", other_plan),
    ))
    previews = (PreviewSession(chapter_plan), PreviewSession(other_plan))
    dialog = _PreviewDialog(qt, planned, previews, translator)
    dialog.dialog.show()
    app.processEvents()
    expected_focus_order = (
        dialog.file_filter, dialog.category_filter, dialog.risk_filter,
        dialog.source_filter, dialog.status_filter, dialog.search_input,
        dialog.clear_filters_button, dialog.table_view,
    )
    focus_order = []
    current = dialog.file_filter
    for _index in range(100):
        if any(current is widget for widget in expected_focus_order):
            focus_order.append(current)
        current = current.nextInFocusChain()
        if current is dialog.file_filter:
            break
    assert focus_order == list(expected_focus_order), [
        type(widget).__name__ for widget in focus_order]

    dialog.source_filter.setCurrentIndex(dialog.source_filter.findData("UserRule:alpha"))
    dialog.status_filter.setCurrentIndex(dialog.status_filter.findData("undecided"))
    dialog.search_input.setText("needle")
    loop = QEventLoop()
    QTimer.singleShot(240, loop.quit)
    loop.exec()
    assert tuple(change.change_id for _preview, change in dialog._visible_entries_cache) == (
        "filter-1", "filter-2")
    dialog._set_current_row(0)
    dialog.accept_this_button.click()
    app.processEvents()
    assert tuple(change.change_id for _preview, change in dialog._visible_entries_cache) == (
        "filter-2",)
    assert dialog._current_entry()[1].change_id == "filter-2"
    assert not dialog.apply_button.isEnabled()
    dialog.undo_button.click()
    app.processEvents()
    assert all(preview.decision("filter-1") is None for preview in previews[:1])
    assert tuple(change.change_id for _preview, change in dialog._visible_entries_cache) == (
        "filter-1", "filter-2")
    dialog.redo_button.click()
    app.processEvents()
    assert previews[0].decision("filter-1").value == "accept_this"
    assert tuple(change.change_id for _preview, change in dialog._visible_entries_cache) == (
        "filter-2",)
    assert all(shortcut.parent() is dialog.table_view for shortcut in dialog._shortcuts)
    widget_shortcut = getattr(Qt, "ShortcutContext", None)
    expected_shortcut_context = getattr(widget_shortcut, "WidgetWithChildrenShortcut", None)
    assert expected_shortcut_context is not None
    assert all(shortcut.context() == expected_shortcut_context for shortcut in dialog._shortcuts)
    dialog.status_filter.setCurrentIndex(dialog.status_filter.findData("accepted"))
    assert tuple(change.change_id for _preview, change in dialog._visible_entries_cache) == (
        "filter-1",)
    assert dialog.reset_current_button.isEnabled()
    dialog.reset_current_button.click()
    app.processEvents()
    assert previews[0].decision("filter-1") is None
    assert dialog._visible_entries_cache == ()
    dialog.undo_button.click()
    app.processEvents()
    assert previews[0].decision("filter-1").value == "accept_this"
    assert tuple(change.change_id for _preview, change in dialog._visible_entries_cache) == (
        "filter-1",)
    dialog.search_input.setText("no such change")
    loop = QEventLoop()
    QTimer.singleShot(240, loop.quit)
    loop.exec()
    assert dialog.filter_count_label.text() == translator.text(
        "preview.visible_count", visible=0, total=3)
    assert dialog.detail.toPlainText() == translator.text("preview.no_filter_matches")
    dialog.clear_filters_button.click()
    app.processEvents()
    assert len(dialog._visible_entries_cache) == 3
    assert not dialog.search_input.text()
    dialog.dialog.grab().save(str(output_dir / f"preview-filter-cleared-{language}.png"))
    dialog.dialog.hide()
    return {
        "filter_controls_follow_tab_order": True,
        "source_status_and_debounced_search_combine": True,
        "decided_row_hides_and_focus_moves_to_next_change": True,
        "preview_undo_redo_buttons_and_table_scoped_shortcuts": True,
        "reset_current_restores_whole_group_and_is_undoable": True,
        "global_apply_guard_and_empty_state": True,
        "clear_filters_restores_all_rows": True,
    }


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
        item["group_actions"] = exercise_group_actions(qt, app, language)
        item["filter_interactions"] = exercise_filters(qt, app, language, args.output)
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
            assert all(item["group_actions"].values()), item
            assert all(item["filter_interactions"].values()), item


if __name__ == "__main__":
    main()
