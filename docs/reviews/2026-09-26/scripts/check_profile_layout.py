"""Real Qt profile search/compare acceptance evidence."""

import argparse
import json
import os
import platform
from pathlib import Path
import subprocess
import sys
import tempfile

import PySide6
from PySide6.QtTest import QTest

from app.profiles import Profile, ProfileStore
from opencc_backend.configs import SUPPORTED_CONFIGS
from ui import profile_window
from ui.i18n import Translator, profile_display_name
from ui.profile_window import ProfileManagerDialog
from ui.qt import ensure_application, load_qt


def _profiles():
    values = []
    for index in range(200):
        values.append(Profile(
            id=f"profile-{index:03d}",
            name=("重名 long English profile " + str(index // 2)
                  if index % 2 == 0 else f"方案 {index} 台湾词汇"),
            conversion="s2tw" if index == 199 else "s2t",
            scope="single" if index == 199 else "all_xhtml",
            ruleset_ids=("default", "candidate") if index == 199 else
                        ("default", "other") if index == 150 else ("default",),
            extras=(("diagnose_mixed", False),) if index == 199 else (),
            force_pivot=index == 199,
            pivot_chain=("t2s", "s2tw") if index == 199 else (),
        ))
    return tuple(values)


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
    profiles = _profiles()
    translator = Translator("en")
    current = Profile(id="current-run", name="Current settings", conversion="s2t",
                      scope="selected", ruleset_ids=("default", "session"),
                      extras=(("diagnose_mixed", True),))
    manager = ProfileManagerDialog(
        qt, profiles, translator=translator, selected_id="profile-199",
        current_profile=current, available_configs=SUPPORTED_CONFIGS,
        available_rulesets=("session", "candidate", "other"),
    )
    manager.dialog.resize(options.width, options.height)
    manager.dialog.show()
    app.processEvents()

    manager.search_edit.setText("profile-199")
    app.processEvents()
    filtered_id = manager._current().id if manager._current() else None
    filter_count = manager.profile_list.count()
    compare_text = manager.comparison_summary.toPlainText()
    comparison_has_direction = "Direction" in compare_text and "→" in compare_text
    comparison_has_rules = "session" in compare_text and "candidate" in compare_text
    comparison_has_panel_option = "Diagnose mixed scripts" in compare_text
    comparison_has_force_pivot = "Force pivot" in compare_text
    manager.detail_tabs.setCurrentIndex(1)
    manager.dialog.grab().save(str(options.output / "profiles-compare.png"))
    manager.rules_checks["candidate"].setChecked(False)
    manager.rules_checks["session"].setChecked(True)
    app.processEvents()
    temporary_rules_update = (
        "candidate" not in manager.comparison_summary.toPlainText()
        and manager.rules_checks["candidate"].isChecked() is False
    )
    temporary_rules_consistent = "Rule sets:" not in manager.comparison_summary.toPlainText()
    manager.search_edit.setText("")
    app.processEvents()
    visible_ids = [manager.profile_list.item(row).data(qt.Qt.UserRole)
                   for row in range(manager.profile_list.count())]
    sorted_ids = [profile.id for profile in sorted(
        profiles, key=lambda item: (profile_display_name(item, translator).casefold(), item.id))]
    list_sorted_by_name = visible_ids == sorted_ids
    row_other = next(row for row in range(manager.profile_list.count())
                     if manager.profile_list.item(row).data(qt.Qt.UserRole) == "profile-150")
    manager.profile_list.setCurrentRow(row_other)
    app.processEvents()
    rulesets_reloaded = (
        manager._current().id == "profile-150"
        and manager.rules_checks["other"].isChecked()
        and not manager.rules_checks["candidate"].isChecked()
    )
    row_candidate = next(row for row in range(manager.profile_list.count())
                         if manager.profile_list.item(row).data(qt.Qt.UserRole) == "profile-199")
    manager.profile_list.setCurrentRow(row_candidate)
    app.processEvents()

    manager.search_edit.setText("does-not-exist")
    app.processEvents()
    empty_state = (
        manager._current() is None
        and manager.empty_label.isVisible()
        and all(not button.isEnabled() for button in (
            manager.use_button, manager.copy_button, manager.rename_button,
            manager.delete_button))
    )
    manager.search_edit.setText("profile-199")
    app.processEvents()
    manager.search_edit.setText("")
    app.processEvents()
    restored_id = manager._current().id if manager._current() else None
    manager.search_edit.setText("profile-199")
    app.processEvents()
    QTest.mouseClick(manager.use_button, qt.Qt.MouseButton.LeftButton)
    app.processEvents()
    use_id = manager.selected.id if manager.selected else None

    with tempfile.TemporaryDirectory(prefix="profile-evidence-") as tmp:
        store = ProfileStore(Path(tmp) / "profiles")
        for profile in profiles:
            store.save(profile)
        delete_manager = ProfileManagerDialog(
            qt, profiles, translator=translator, store=store,
            selected_id="profile-198", current_profile=current,
            available_configs=SUPPORTED_CONFIGS,
        )
        delete_manager.dialog.show()
        delete_manager.search_edit.setText("profile-198")
        app.processEvents()
        deleted_selected_id = delete_manager._current().id
        original_confirmation = profile_window.ask_confirmation
        profile_window.ask_confirmation = lambda *_args: True
        delete_manager._delete()
        profile_window.ask_confirmation = original_confirmation
        delete_exact_id = (
            deleted_selected_id == "profile-198"
            and not store._path("profile-198").exists()
            and store._path("profile-197").exists()
        )

        copy_manager = ProfileManagerDialog(
            qt, profiles, translator=translator, store=store,
            selected_id="profile-197", current_profile=current,
            available_configs=SUPPORTED_CONFIGS,
        )
        copy_manager.dialog.show()
        copy_manager.search_edit.setText("profile-197")
        app.processEvents()
        original_input = qt.QInputDialog
        qt.QInputDialog = type("InputDialog", (), {
            "getText": staticmethod(lambda *_args, **_kwargs: ("Copied from 197", True)),
        })
        copy_source_id = copy_manager._current().id
        copy_manager._copy()
        qt.QInputDialog = original_input
        copied = next((item for item in copy_manager._profiles
                       if item.name == "Copied from 197"), None)
        copy_exact_id = (
            copy_source_id == "profile-197" and copied is not None
            and copied.conversion == next(item for item in profiles
                                          if item.id == "profile-197").conversion
        )

    unavailable_profile = Profile(
        id="unavailable-jieba", name="Unavailable Jieba",
        conversion="s2twp_jieba", segmentation="jieba")
    unavailable_manager = ProfileManagerDialog(
        qt, (unavailable_profile,), translator=translator,
        selected_id=unavailable_profile.id, current_profile=current,
        available_configs=("s2t",), jieba_pending=True,
    )
    unavailable_text = unavailable_manager.summary.toPlainText()
    unavailable_view_kept = (
        unavailable_manager._current().conversion == "s2twp_jieba"
        and unavailable_manager.use_button.isEnabled()
        and "checking availability" in unavailable_text
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
        "git_head": subprocess.run(["git", "rev-parse", "HEAD"], check=True,
                                    capture_output=True, text=True).stdout.strip(),
        "requested_window": [options.width, options.height],
        "profile_count": len(profiles),
        "filter_count": filter_count,
        "filtered_current_id": filtered_id,
        "comparison_has_direction": comparison_has_direction,
        "comparison_has_rules": comparison_has_rules,
        "comparison_has_panel_option": comparison_has_panel_option,
        "comparison_has_force_pivot": comparison_has_force_pivot,
        "temporary_ruleset_updates_comparison": temporary_rules_update,
        "temporary_ruleset_can_match_current_run": temporary_rules_consistent,
        "new_profile_selection_reloads_rulesets": rulesets_reloaded,
        "list_is_sorted_by_display_name": list_sorted_by_name,
        "empty_filter_disables_actions": empty_state,
        "clearing_search_restores_profile_id": restored_id == "profile-199",
        "use_after_filter_uses_profile_id": use_id == "profile-199",
        "delete_after_filter_hits_exact_id": delete_exact_id,
        "copy_after_filter_copies_exact_id": copy_exact_id,
        "unavailable_jieba_remains_visible_and_unmodified": unavailable_view_kept,
    }
    (options.output / "profiles.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if options.verify:
        assert all(value for key, value in report.items()
                   if key not in {"PySide6", "python", "platform", "qpa_platform",
                                  "screen_geometry", "screen_device_pixel_ratio",
                                  "git_head", "requested_window", "profile_count",
                                  "filter_count", "filtered_current_id"}), report
        assert filter_count == 1, report
        assert filtered_id == "profile-199", report
        assert filter_count < len(profiles), report
        assert restored_id == "profile-199", report


if __name__ == "__main__":
    main()
