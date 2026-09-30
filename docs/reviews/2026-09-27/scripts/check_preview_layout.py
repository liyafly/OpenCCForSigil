"""Measure real Qt preview geometry; optional acceptance checks for Luna."""

import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "plugin/OpenCCForSigil"))

import PySide6  # noqa: E402
from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402
from core.models import ConversionPlan, Diagnostic, SourceSpan, TokenChange  # noqa: E402
from core.preview import PreviewSession  # noqa: E402
from ui.i18n import Translator  # noqa: E402
from ui.preview_window import _PreviewDialog  # noqa: E402
from ui.qt import ensure_application, load_qt  # noqa: E402


def complete_batch_dialog(
    qt, app, translator, dialog, *, scope=None, confirm=True,
    output_dir=None, screenshot=None,
):
    action = dialog._more_action_by_button[dialog.batch_button]
    assert action.isEnabled()
    details = {}

    def interact():
        modal = app.activeModalWidget()
        assert modal is not None
        combos = modal.findChildren(qt.QComboBox)
        check = modal.findChild(qt.QCheckBox)
        labels = modal.findChildren(qt.QLabel)
        buttons = modal.findChildren(qt.QPushButton)
        assert len(combos) == 2 and check is not None and check.isChecked()
        if screenshot is not None:
            app.processEvents()
            modal.grab().save(str(output_dir / screenshot))
        if scope is not None:
            combos[0].setCurrentIndex(combos[0].findData(scope))
        summary_prefix = translator.text(
            "preview.batch_summary_main_many_files",
            action="", changes=1, files=1,
        ).split("1")[0].strip()
        details["summary"] = next(label.text() for label in labels
                                   if label.text().startswith(summary_prefix))
        confirm_button = next(button for button in buttons
                              if button.text().startswith(
                                  translator.text("preview.batch_confirm").split("{")[0])
                              or button.text().startswith(
                                  translator.text("preview.batch_confirm_overwrite").split("{")[0]))
        details["enabled"] = confirm_button.isEnabled()
        (confirm_button if confirm else next(
            button for button in buttons
            if button.text() == translator.text("common.cancel"))).click()

    QTimer.singleShot(0, interact)
    action.trigger()
    app.processEvents()
    return details


def exercise_batch_decisions(qt, app, language, output_dir):
    translator = Translator(language)

    def make_dialog(changes):
        by_file = {}
        for change in changes:
            by_file.setdefault(change.file_id, []).append(change)
        plans = tuple(ConversionPlan(source_sha256="", file_id=file_id,
                                     changes=tuple(items))
                      for file_id, items in by_file.items())
        planned = tuple(SimpleNamespace(
            source=SimpleNamespace(file_id=plan.file_id, href=plan.file_id,
                                   document_kind="xhtml"), plan=plan,
        ) for plan in plans)
        previews = tuple(PreviewSession(plan) for plan in plans)
        return _PreviewDialog(qt, planned, previews, translator), previews

    plain = [TokenChange(source="a", target="b", span=SourceSpan(0, 1),
                         rule_source="fixture", change_id=f"b1-{i}",
                         file_id="chapter") for i in range(10)]
    dialog, previews = make_dialog(plain)
    for change in plain[:2]:
        previews[0].accept_this(change.change_id)
    for change in plain[2:5]:
        previews[0].reject_this(change.change_id)
    dialog._recompute_counts()
    b1 = complete_batch_dialog(
        qt, app, translator, dialog,
        output_dir=output_dir, screenshot=f"batch-b1-dialog-{language}.png")
    assert b1["enabled"] and "5" in b1["summary"]
    assert sum((decision := previews[0].decision(change.change_id)) is not None
               and decision.value.startswith("accept") for change in plain) == 7
    assert sum((decision := previews[0].decision(change.change_id)) is not None
               and decision.value.startswith("reject") for change in plain) == 3
    dialog._undo_preview_action()
    assert sum(previews[0].decision(change.change_id) is None for change in plain) == 5
    assert sum((decision := previews[0].decision(change.change_id)) is not None
               and decision.value.startswith("accept") for change in plain) == 2
    assert sum((decision := previews[0].decision(change.change_id)) is not None
               and decision.value.startswith("reject") for change in plain) == 3
    dialog.dialog.hide()

    remaining_changes = [TokenChange(
        source="a", target="b", span=SourceSpan(0, 1),
        rule_source="fixture", change_id=f"remaining-{index}",
        file_id="chapter",
    ) for index in range(10)]
    dialog, previews = make_dialog(remaining_changes)
    for change in remaining_changes[:2]:
        previews[0].accept_this(change.change_id)
    for change in remaining_changes[2:5]:
        previews[0].reject_this(change.change_id)
    dialog._recompute_counts()
    dialog._update_summary()
    dialog.dialog.show()
    dialog.dialog.activateWindow()
    app.processEvents()
    assert dialog.resolve_remaining_button.isVisible()
    assert "5" in dialog.resolve_remaining_button.text()
    menu_labels = [action.text() for action in dialog.more_menu.actions()]
    assert translator.text("preview.batch_decide") in menu_labels
    assert menu_labels.count(translator.text("preview.batch_decide")) == 1
    assert not any(hasattr(dialog, name) for name in (
        "accept_file_button", "reject_file_button", "accept_filter_button",
        "reject_filter_button", "accept_all_button", "reject_all_button",
    ))
    assert sum(action.isVisible() for action in dialog.more_menu.actions()) <= 4
    dialog.dialog.grab().save(str(output_dir / f"resolve-remaining-{language}.png"))
    resolve_details = {}

    def resolve_remaining_once():
        modal = app.activeModalWidget()
        assert modal is not None
        combos = modal.findChildren(qt.QComboBox)
        check = modal.findChild(qt.QCheckBox)
        assert len(combos) == 2 and check is not None and check.isChecked()
        assert combos[0].currentData() == "all"
        expected_summary = translator.text(
            "preview.batch_summary_main_many_one_file",
            action=translator.text("preview.batch_action_accept"),
            changes=5,
            files=1,
        )
        assert expected_summary in [
            label.text() for label in modal.findChildren(qt.QLabel)
        ]
        resolve_details["summary"] = expected_summary
        buttons = modal.findChildren(qt.QPushButton)
        confirm_button = next(button for button in buttons if button.text().startswith(
            translator.text("preview.batch_confirm").split("{")[0])
            or button.text().startswith(
                translator.text("preview.batch_confirm_overwrite").split("{")[0]))
        confirm_button.click()

    QTimer.singleShot(0, resolve_remaining_once)
    dialog.resolve_remaining_button.click()
    app.processEvents()
    assert all(previews[0].decision(change.change_id).value.startswith("accept")
               for change in remaining_changes[:2] + remaining_changes[5:])
    assert all(previews[0].decision(change.change_id).value.startswith("reject")
               for change in remaining_changes[2:5])
    assert dialog.apply_button.isEnabled()
    assert len(dialog._undo_stack) == 1
    assert resolve_details["summary"]
    dialog._undo_preview_action()
    assert all(previews[0].decision(change.change_id) is None
               for change in remaining_changes[5:])
    dialog.dialog.hide()

    grouped = [TokenChange(source="a", target="b", span=SourceSpan(0, 1),
                           rule_source="fixture", change_id=f"b3-{i}",
                           file_id=f"file-{i}", group_id="rules:batch")
               for i in range(3)]
    dialog, previews = make_dialog(grouped)
    dialog._visible_entries_cache = (dialog._entries[0],)
    cancelled = complete_batch_dialog(qt, app, translator, dialog, confirm=False)
    assert cancelled["enabled"] and "2" in cancelled["summary"]
    assert all(preview.decision(change.change_id) is None
               for preview, change in dialog._entries)
    b3 = complete_batch_dialog(qt, app, translator, dialog)
    assert b3["enabled"] and "2" in b3["summary"]
    assert all(preview.decision(change.change_id).value.startswith("accept")
               for preview, change in dialog._entries)
    dialog._undo_preview_action()
    assert all(preview.decision(change.change_id) is None
               for preview, change in dialog._entries)
    dialog.dialog.hide()

    b5_changes = [
        TokenChange(source="a", target="b", span=SourceSpan(0, 1),
                    rule_source="UserRule", change_id="local-1", file_id="chapter",
                    group_id="rules:local"),
        TokenChange(source="a", target="b", span=SourceSpan(0, 1),
                    rule_source="UserRule", change_id="local-2", file_id="chapter",
                    group_id="rules:local"),
        TokenChange(source="zh-CN", target="zh-TW", span=SourceSpan(0, 5),
                    rule_source="language_metadata", change_id="lang-chapter",
                    file_id="chapter", group_id="language_metadata"),
        TokenChange(source="zh-CN", target="zh-TW", span=SourceSpan(0, 5),
                    rule_source="language_metadata", change_id="lang-opf",
                    file_id="content.opf", group_id="language_metadata"),
    ]
    dialog, previews = make_dialog(b5_changes)
    b5_file = complete_batch_dialog(qt, app, translator, dialog, scope="file")
    assert b5_file["enabled"]
    assert sum(preview.summary()["accepted"] for preview in previews) == 2
    assert sum(preview.summary()["undecided"] for preview in previews) == 2
    dialog._undo_preview_action()
    b5_all = complete_batch_dialog(qt, app, translator, dialog, scope="all")
    assert b5_all["enabled"]
    assert sum(preview.summary()["accepted"] for preview in previews) == 4
    dialog.dialog.hide()

    stale_changes = [TokenChange(source="a", target="b", span=SourceSpan(0, 1),
                                 rule_source="fixture", change_id=f"stale-{index}",
                                 file_id="chapter") for index in range(2)]
    dialog, previews = make_dialog(stale_changes)
    stale_details = {}

    def click_confirmation(expect_stale):
        modal = app.activeModalWidget()
        assert modal is not None
        labels = modal.findChildren(qt.QLabel)
        buttons = modal.findChildren(qt.QPushButton)
        stale_details["stale_visible"] = any(
            translator.text("preview.batch_stale") in label.text() for label in labels)
        confirm_button = next(
            button for button in buttons
            if button.text().startswith(
                translator.text("preview.batch_confirm").split("{")[0])
            or button.text().startswith(
                translator.text("preview.batch_confirm_overwrite").split("{")[0]))
        assert confirm_button.isEnabled()
        assert stale_details["stale_visible"] is expect_stale
        confirm_button.click()

    def change_then_confirm():
        previews[0].accept_this(stale_changes[0].change_id)
        click_confirmation(False)
        QTimer.singleShot(30, lambda: click_confirmation(True))

    QTimer.singleShot(0, change_then_confirm)
    dialog._more_action_by_button[dialog.batch_button].trigger()
    assert previews[0].decision("stale-0").value == "accept_this"
    assert previews[0].decision("stale-1").value == "accept_this"
    assert len(dialog._undo_stack) == 1
    dialog._undo_preview_action()
    assert previews[0].decision("stale-0").value == "accept_this"
    assert previews[0].decision("stale-1") is None
    dialog.dialog.hide()

    return {"B1": "real QAction, exact counts and one-step Undo",
            "UXS-03": "all-scope remaining button preserves manual skips; apply unlocks after one confirmation",
            "B3": "Cancel preserved decisions; filtered hit expanded group and Undo restored",
            "B5": "file scope included local rules and excluded language group; all scope included it",
            "B10": "stale decision revision refreshed and required a second confirmation"}


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
    assert not hasattr(dialog, "accept_group_button")
    assert not hasattr(dialog, "_group_more_actions")
    selected_row = next(
        index for index, (_preview, change) in enumerate(dialog._visible_entries_cache)
        if change.change_id == "language-chapter")
    dialog._set_current_row(selected_row)
    dialog.accept_this_button.click()
    app.processEvents()
    assert all(previews[index].decision(change.change_id).value == "accept_this"
               for index, change in enumerate((language_changes[0], language_changes[1])))
    assert all(previews[0].decision(change.change_id) is None for change in rule_changes)

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
    assert not hasattr(rule_only, "accept_group_button")
    assert not hasattr(rule_only, "_group_more_actions")
    assert all(rule_only._previews[0].decision(change.change_id) is None
               for change in rule_changes)
    complete_batch_dialog(qt, app, translator, rule_only, scope="file")
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

    assert dialog.undo_button.isEnabled()
    dialog.undo_button.click()
    app.processEvents()
    assert all(preview.decision(change.change_id) is None
               for preview, change in zip(previews, language_changes))
    assert dialog.redo_button.isEnabled()
    dialog.redo_button.click()
    app.processEvents()
    assert all(previews[0].decision(change.change_id).value == "accept_this"
               for change in language_changes[:1])
    assert previews[1].decision(language_changes[1].change_id).value == "accept_this"
    assert all(previews[0].decision(change.change_id) is None for change in rule_changes)
    complete_batch_dialog(qt, app, translator, dialog, scope="file")
    app.processEvents()
    assert all(previews[0].decision(change.change_id).value == "accept_this"
               for change in rule_changes)
    dialog.dialog.hide()

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

    cancelled = complete_batch_dialog(
        qt, app, translator, filtered, scope="filtered", confirm=False)
    assert translator.text(
        "preview.batch_summary_part_hidden", count=1) in cancelled["summary"]
    app.processEvents()
    assert all(preview.decision(preview.changes[0].change_id) is None
               for preview in filtered_previews)
    complete_batch_dialog(qt, app, translator, filtered, scope="filtered")
    app.processEvents()
    assert all(preview.decision(preview.changes[0].change_id).value == "accept_this"
               for preview in filtered_previews)
    filtered.dialog.hide()
    return {
        "language_group_action_buttons_removed": True,
        "language_item_action_decides_group_across_files_and_undoes_as_one": True,
        "language_item_action_leaves_rule_group_pending": True,
        "file_batch_action_still_accepts_rule_changes_and_undoes": True,
        "file_batch_completes_local_rule_group": True,
        "batch_hidden_group_summary_cancel_preserves_and_confirm_expands": True,
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
        dialog.status_filter, dialog.search_input, dialog.clear_filters_button,
        dialog.more_filters_button, dialog.file_filter, dialog.category_filter,
        dialog.risk_filter, dialog.source_filter, dialog.table_view,
    )
    focus_order = []
    dialog.more_filters_button.click()
    app.processEvents()
    current = dialog.status_filter
    for index in range(30):
        if index and current is dialog.status_filter:
            break
        if any(current is widget for widget in expected_focus_order):
            focus_order.append(current)
        current = current.nextInFocusChain()
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
    batch_state = {}

    def inspect_empty_filtered_batch():
        modal = app.activeModalWidget()
        assert modal is not None
        buttons = modal.findChildren(qt.QPushButton)
        confirm_prefixes = tuple(
            translator.text(key).split("{")[0]
            for key in (
                "preview.batch_confirm", "preview.batch_confirm_overwrite",
                "preview.batch_confirm_none",
            )
        )
        confirm = next(button for button in buttons
                       if any(button.text().startswith(prefix)
                              for prefix in confirm_prefixes))
        batch_state["enabled"] = confirm.isEnabled()
        next(button for button in buttons
             if button.text() == translator.text("common.cancel")).click()

    QTimer.singleShot(0, inspect_empty_filtered_batch)
    dialog.batch_button.click()
    app.processEvents()
    assert batch_state["enabled"] is False
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


def exercise_export_options(qt, app, language):
    translator = Translator(language)
    change = TokenChange(
        source="软件", target="軟體", span=SourceSpan(0, 2),
        rule_source="OpenCC:s2t", change_id="export-change", file_id="chapter",
    )
    plan = ConversionPlan(source_sha256="", file_id="chapter", changes=(change,))
    planned = (SimpleNamespace(
        source=SimpleNamespace(file_id="chapter", href="Text/chapter.xhtml",
                               document_kind="xhtml"), plan=plan),)
    calls = []
    services = SimpleNamespace(export_preview=lambda *_args: calls.append(_args[2]))
    dialog = _PreviewDialog(qt, planned, (PreviewSession(plan),), translator, services)
    export_action = dialog._more_action_by_button[dialog.export_button]
    assert export_action.isEnabled()

    def answer(mode):
        modal = app.activeModalWidget()
        assert modal is not None
        checkbox = modal.findChild(qt.QCheckBox)
        assert checkbox is not None and not checkbox.isChecked()
        if mode == "cancel":
            button = next(item for item in modal.findChildren(qt.QPushButton)
                          if item.text() == translator.text("common.cancel"))
            button.click()
        else:
            checkbox.setChecked(True)
            button = next(item for item in modal.findChildren(qt.QPushButton)
                          if item.text() == translator.text("preview.export"))
            button.click()

    QTimer.singleShot(0, lambda: answer("cancel"))
    export_action.trigger()
    assert calls == []
    QTimer.singleShot(0, lambda: answer("export"))
    export_action.trigger()
    assert calls == [True]
    return {"menu_action_opens_options": True, "cancel_is_noop": True,
            "full_diff_resets_off_and_is_opt_in": True}


def exercise_diagnostics(qt, app, language, output_dir):
    translator = Translator(language)
    source = "<p>甲<em>乙</em></p>"
    changes = (
        TokenChange(
            source="甲", target="乙", span=SourceSpan(3, 4), rule_source="OpenCC:s2t",
            change_id="diagnostic-first", file_id="changed",
        ),
        TokenChange(
            source="乙", target="丙", span=SourceSpan(8, 9), rule_source="OpenCC:s2t",
            change_id="diagnostic-second", file_id="changed",
        ),
    )
    changed_plan = ConversionPlan(
        source_sha256="", file_id="changed", changes=changes,
        diagnostics=(
            Diagnostic("INLINE_BOUNDARY", "fixture", SourceSpan(4, 8)),
            Diagnostic("QUOTE_UNBALANCED", "fixture", SourceSpan(8, 9)),
        ),
    )
    no_change_plan = ConversionPlan(
        source_sha256="", file_id="diagnostic-only", changes=(),
        diagnostics=(Diagnostic("MIXED_SCRIPT", "fixture", SourceSpan(0, 5)),),
    )
    planned = tuple(SimpleNamespace(
        source=SimpleNamespace(file_id=file_id, href=href, document_kind="xhtml",
                               source=source_text),
        plan=plan,
    ) for file_id, href, source_text, plan in (
        ("changed", "Text/changed.xhtml", source, changed_plan),
        ("diagnostic-only", "Text/diagnostic-only.xhtml", "plain source", no_change_plan),
    ))
    previews = (PreviewSession(changed_plan), PreviewSession(no_change_plan))
    dialog = _PreviewDialog(qt, planned, previews, translator)
    dialog.dialog.show()
    app.processEvents()
    diagnostics_tab = dialog._diagnostic_tab_index
    assert diagnostics_tab is not None
    dialog.detail_tabs.setCurrentIndex(diagnostics_tab)
    app.processEvents()
    panel = dialog.diagnostic_panel
    assert panel is not None
    assert not panel.content.isVisible()
    panel.toggle.click()
    app.processEvents()
    assert panel.content.isVisible()
    assert panel.table.rowCount() == 3
    assert panel._visible_records[0].location == translator.text(
        "preview.invalid_source_location", line=1, column=5)

    # A click reveals the linked change; keyboard navigation moves to the
    # following diagnostic and selects its real matching preview change.
    panel.table.cellClicked.emit(0, 0)
    assert dialog._selected_change_identity() == ("changed", "diagnostic-first")
    assert previews[0].decision("diagnostic-first") is None
    panel.table.setFocus()
    key_press = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key_Down, Qt.KeyboardModifier.NoModifier)
    key_release = QKeyEvent(
        QEvent.Type.KeyRelease, Qt.Key_Down, Qt.KeyboardModifier.NoModifier)
    QCoreApplication.sendEvent(panel.table, key_press)
    QCoreApplication.sendEvent(panel.table, key_release)
    app.processEvents()
    assert dialog._selected_change_identity() == ("changed", "diagnostic-second")
    assert previews[0].decision("diagnostic-second") is None

    panel.file_filter.setCurrentIndex(panel.file_filter.findData("diagnostic-only"))
    app.processEvents()
    assert panel.table.rowCount() == 1
    assert panel._visible_records[0].file_id == "diagnostic-only"
    panel.table.cellClicked.emit(0, 0)
    assert dialog._selected_change_identity() == ("changed", "diagnostic-second")
    assert "【plain】 source" in panel.context.toPlainText()
    dialog.detail_tabs.setCurrentIndex(1)
    app.processEvents()
    dialog.dialog.grab().save(str(output_dir / f"preview-diagnostics-{language}.png"))
    panel.toggle.click()
    app.processEvents()
    assert not panel.content.isVisible()
    dialog.dialog.hide()

    events = []

    def click_result_diagnostics():
        modal = app.activeModalWidget()
        assert isinstance(modal, QMessageBox)
        button = next(
            button for button in modal.buttons()
            if button.text() == translator.text("result.view_diagnostics"))
        events.append("opened")
        button.click()

    def close_diagnostics():
        modal = app.activeModalWidget()
        assert modal is not None and not isinstance(modal, QMessageBox)
        button = next(
            button for button in modal.findChildren(qt.QPushButton)
            if button.text() == translator.text("common.close"))
        events.append("diagnostics_closed")
        button.click()

    def close_result():
        modal = app.activeModalWidget()
        assert isinstance(modal, QMessageBox)
        button = next(
            button for button in modal.buttons()
            if button.text() == translator.text("common.close"))
        events.append("result_closed")
        button.click()

    QTimer.singleShot(0, click_result_diagnostics)
    QTimer.singleShot(100, close_diagnostics)
    QTimer.singleShot(250, close_result)
    from ui.preview_window import show_result
    result = show_result(
        status="success", files_scanned=1, files_changed=0,
        accepted_changes=0, skipped_changes=0, return_to_scope=True,
        diagnostic_documents=(planned[1],), translator=translator,
    )
    assert result == "close"
    assert events == ["opened", "diagnostics_closed", "result_closed"]
    return {
        "collapsed_by_default_and_expandable": True,
        "file_filter_includes_no_change_diagnostics": True,
        "click_and_keyboard_navigation_select_real_preview_rows": True,
        "diagnostic_selection_does_not_change_decisions": True,
        "zero_change_result_opens_and_closes_diagnostics": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=640)
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
        window.dialog.resize(args.width, args.height)
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
        item["batch_decisions"] = exercise_batch_decisions(
            qt, app, language, args.output)
        item["filter_interactions"] = exercise_filters(qt, app, language, args.output)
        item["diagnostic_interactions"] = exercise_diagnostics(
            qt, app, language, args.output)
        item["export_interactions"] = exercise_export_options(qt, app, language)
        results.append(item)
        window.dialog.hide()
    screen = app.primaryScreen()
    geometry = screen.availableGeometry() if screen is not None else None
    report = {
        "head": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            capture_output=True, text=True).stdout.strip(),
        "PySide6": PySide6.__version__,
        "os": platform.platform(),
        "qpa": os.environ.get("QT_QPA_PLATFORM", "default"),
        "screen_available": ([geometry.width(), geometry.height()]
                             if geometry is not None else None),
        "device_pixel_ratio": screen.devicePixelRatio() if screen is not None else None,
        "results": results,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (args.output / "layout.json").write_text(text, encoding="utf-8")
    print(text, end="")
    if args.verify:
        for item in results:
            assert item["minimum_width"] <= 1000, item
            assert item["minimum_height"] < 600, item
            # A requested 1280×800 logical size is intentionally retained in
            # offscreen tests even when the synthetic screen reports 800×800;
            # it is not evidence of physical-screen clamping.
            assert item["initial_width"] <= max(1200, args.width), item
            assert item["initial_height"] <= max(720, args.height), item
            assert item["table_height"] >= 150, item
            assert all(item["group_actions"].values()), item
            assert all(item["filter_interactions"].values()), item
            assert all(item["diagnostic_interactions"].values()), item
            assert all(item["export_interactions"].values()), item


if __name__ == "__main__":
    main()
