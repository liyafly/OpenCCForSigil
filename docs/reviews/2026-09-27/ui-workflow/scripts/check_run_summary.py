"""Exercise the merged scope/settings summary and read-only detail view in real Qt."""

import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "plugin/OpenCCForSigil"))

import PySide6  # noqa: E402
from PySide6.QtCore import QTimer, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from app.profiles import Profile  # noqa: E402
from app.settings import RunSettings  # noqa: E402
from opencc_backend.backend import OpenCCBackend  # noqa: E402
from sigil.scope import TextFile  # noqa: E402
from ui import preview_window  # noqa: E402
from ui import run_options as run_options_module  # noqa: E402
from ui.i18n import Translator  # noqa: E402
from ui.qt import ensure_application, load_qt  # noqa: E402


class MetadataAdapter:
    def __init__(self):
        self.reads = []
        self.writes = []

    def text_file_inventory(self):
        return (TextFile("chapter", "Text/chapter.xhtml"),
                TextFile("nav", "Text/nav.xhtml"))

    def selected_ids(self):
        return ("chapter",)

    def text_files(self, _scope):
        return (("chapter", "Text/chapter.xhtml"), ("nav", "Text/nav.xhtml"))

    def nav_id(self):
        return "nav"

    def readfile(self, file_id):
        self.reads.append(file_id)
        return "<p>must not be read</p>"

    def writefile(self, file_id, _value):
        self.writes.append(file_id)


class Probe:
    def __init__(self, state):
        self.state = state

    def jieba_probe_state(self):
        return self.state, "fixture unavailable" if self.state == "unavailable" else None, 1

    def available_configs_nonblocking(self):
        return ("s2t_jieba",) if self.state == "available" else ()


def _run_summary(qt, app, language, output_dir, width, height):
    translator = Translator(language)
    adapter = MetadataAdapter()
    counts = {"backend_constructors": 0, "profile_saves": 0}
    original_backend_init = OpenCCBackend.__init__

    def tracked_backend_init(self, *args, **kwargs):
        counts["backend_constructors"] += 1
        return original_backend_init(self, *args, **kwargs)

    OpenCCBackend.__init__ = tracked_backend_init
    try:
        with tempfile.TemporaryDirectory(prefix="opencc-summary-") as temporary:
            root = Path(temporary)
            storage = SimpleNamespace(paths=SimpleNamespace(
                root=root, profiles=root / "profiles", rules=root / "rules"))
            services = RunSettings(storage, adapter, {}, language=language, session_id="probe")
            services.active = Profile(
                id="saved-profile", name="Saved profile", conversion="s2t",
                convert_nav=True, convert_alt=True, convert_metadata=True,
                force_pivot=True, pivot_chain=("t2s", "s2t"), mathml=True,
                ruleset_ids=("default", "a-long-rule-set-id", "second-rule-set"),
            )
            original_save = services.profiles.save

            def tracked_save(*args, **kwargs):
                counts["profile_saves"] += 1
                return original_save(*args, **kwargs)

            services.profiles.save = tracked_save
            captured = {}
            original_scope = preview_window._ScopeDialog
            original_config = preview_window._ConversionConfigDialog

            def capture_scope(*args, **kwargs):
                captured["scope"] = original_scope(*args, **kwargs)
                return captured["scope"]

            def capture_config(*args, **kwargs):
                captured["config"] = original_config(*args, **kwargs)
                return captured["config"]

            preview_window._ScopeDialog = capture_scope
            preview_window._ConversionConfigDialog = capture_config
            outer_dialog = {}
            detail = {}

            def interactive_exec(dialog):
                if dialog is not captured["scope"].dialog:
                    table = getattr(dialog, "change_table", None)
                    if table is not None:
                        dialog.show()
                        app.processEvents()
                        detail_size = dialog.size()
                        detail.setdefault("change_dialog_geometries", []).append(
                            [detail_size.width(), detail_size.height()])
                        role = qt.Qt.ItemDataRole.DisplayRole
                        rows = {}
                        for row in range(table.rowCount()):
                            rows[table.item(row, 0).text()] = tuple(
                                table.item(row, column).data(role)
                                for column in range(1, 4))
                        rule_label = translator.text("profile.rules")
                        rule_row = next(
                            row for row in range(table.rowCount())
                            if table.item(row, 0).text() == rule_label
                        )
                        nav_row = next(
                            row for row in range(table.rowCount())
                            if table.item(row, 0).text() == translator.text("options.include_nav")
                        )
                        rules_tooltip = table.item(rule_row, 1).toolTip()
                        nav_reason_tooltip = table.item(nav_row, 3).toolTip()
                        detail.setdefault("full_value_tooltips", []).append({
                            "rules": rules_tooltip,
                            "nav_effective_reason": nav_reason_tooltip,
                        })
                        assert "a-long-rule-set-id" in rules_tooltip
                        assert nav_reason_tooltip == table.item(nav_row, 3).text()
                        assert translator.text("options.not_effective_reason").split("{")[0] \
                            in nav_reason_tooltip
                        detail.setdefault("tables", []).append(rows)
                        detail["rows"] = rows
                        header = table.horizontalHeader()
                        viewport_width = table.viewport().width()
                        detail["details_columns_visible"] = all(
                            header.sectionViewportPosition(column) >= 0
                            and header.sectionViewportPosition(column)
                            + header.sectionSize(column) <= viewport_width
                            for column in range(table.columnCount()))
                        detail["details_horizontal_scroll_max"] = table.horizontalScrollBar().maximum()
                        assert detail["details_columns_visible"]
                        assert detail["details_horizontal_scroll_max"] == 0
                        dialog.grab().save(str(
                            output_dir / f"settings-details-{language}-{len(detail['tables'])}.png"))
                        dialog.accept()
                    return
                outer_dialog["dialog"] = dialog
                dialog.resize(width, height)
                dialog.show()
                app.processEvents()
                size = dialog.size()
                detail["actual_dialog_geometry"] = [size.width(), size.height()]

                def interact():
                    scope = captured["scope"]
                    config = captured["config"]
                    app.processEvents()
                    summary = next(label for label in dialog.findChildren(qt.QLabel)
                                   if label.text().startswith(translator.text("scope.run_summary").split("{")[0]))
                    detail["initial_summary"] = summary.text()
                    detail["summary_lines"] = summary.text().count("\n") + 1
                    dialog.grab().save(str(output_dir / f"scope-settings-initial-{language}.png"))
                    assert "1" in summary.text().split("\n", 1)[0] and "XHTML" in \
                        summary.text().split("\n", 1)[0]
                    assert translator.text("scope.run_summary_nav_unavailable") in summary.text()
                    assert detail["summary_lines"] <= 2
                    analyze_button = next(
                        button for button in dialog.findChildren(qt.QPushButton)
                        if button.text() == translator.text("config.continue"))
                    assert dialog.windowTitle() == (
                        f"{translator.text('app.title')} — {translator.text('main.title')}")
                    assert analyze_button.text() == translator.text("config.continue")
                    assert config.direction_label.isVisible() and config.combo.isVisible()
                    alternate_language = "zh-Hans" if language != "zh-Hans" else "en"
                    scope.language_combo.setCurrentIndex(
                        scope.language_combo.findData(alternate_language))
                    app.processEvents()
                    detail["translated_main_title"] = dialog.windowTitle()
                    detail["translated_analyze_label"] = analyze_button.text()
                    assert dialog.windowTitle() == (
                        f"{translator.text('app.title')} — {translator.text('main.title')}")
                    assert analyze_button.text() == translator.text("config.continue")
                    assert config.direction_label.text() == translator.text("config.direction")
                    scope.language_combo.setCurrentIndex(scope.language_combo.findData(language))
                    app.processEvents()
                    scope.filter_edit.setText("nav")
                    app.processEvents()
                    QTest.keyClick(scope.filter_edit, Qt.Key.Key_Return)
                    app.processEvents()
                    detail["filter_enter_keeps_dialog_open"] = dialog.isVisible()
                    detail["filter_enter_keeps_scope_unaccepted"] = not scope.accepted
                    detail["filter_enter_focuses_visible_nav"] = (
                        scope.list_widget.currentRow() == 1)
                    assert detail["filter_enter_keeps_dialog_open"]
                    assert detail["filter_enter_keeps_scope_unaccepted"]
                    assert detail["filter_enter_focuses_visible_nav"]
                    scope.filter_edit.clear()
                    scope.list_widget.setCurrentRow(0)
                    app.processEvents()
                    tabs = dialog.findChild(qt.QTabWidget)
                    tabs.setCurrentIndex(1)
                    app.processEvents()
                    dialog.grab().save(str(output_dir / f"conversion-settings-{language}.png"))
                    assert config.options_panel.view_changes_button.isVisible()
                    detail["advanced_text"] = config.options_panel.advanced_button.text()
                    detail["view_changes_clicked"] = True
                    config.options_panel.view_changes_button.click()
                    app.processEvents()
                    nav_values = detail["rows"][translator.text("options.include_nav")]
                    detail["nav_saved_current_effective"] = nav_values
                    mathml_label = translator.text("profile.mathml")
                    detail["mathml_visible_when_unchanged"] = mathml_label in detail["rows"]
                    assert nav_values[0] == translator.text("profile.enabled")
                    assert nav_values[1] == translator.text("profile.enabled")
                    assert translator.text("options.not_effective_reason").split("{")[0] in nav_values[2]
                    assert detail["mathml_visible_when_unchanged"]

                    # A new direction refreshes the summary and marks an enabled
                    # but unsupported force-pivot preference as inactive.
                    config.combo.setCurrentIndex(config.combo.findData("t2jp"))
                    app.processEvents()
                    detail["changed_direction_summary"] = summary.text()
                    assert translator.text("scope.run_summary_risk_pivot_inactive") in summary.text()
                    config.options_panel.view_changes_button.click()
                    app.processEvents()
                    pivot_label = translator.text("options.force_pivot")
                    detail["inactive_pivot_effective"] = detail["rows"][pivot_label][2]
                    assert translator.text("options.not_effective_reason").split("{")[0] in \
                        detail["inactive_pivot_effective"]

                    # Selecting the NAV item changes final XHTML count and inclusion.
                    tabs.setCurrentIndex(0)
                    app.processEvents()
                    scope.selected_radio.click()
                    nav_item = next(scope.list_widget.item(index)
                                    for index in range(scope.list_widget.count())
                                    if scope.list_widget.item(index).data(qt.Qt.ItemDataRole.UserRole) == "nav")
                    nav_item.setCheckState(Qt.CheckState.Checked)
                    app.processEvents()
                    detail["nav_selected_summary"] = summary.text()
                    assert "2" in summary.text().split("\n", 1)[0] and "XHTML" in \
                        summary.text().split("\n", 1)[0]
                    assert translator.text("scope.run_summary_nav_included") in summary.text()
                    language_index = scope.language_combo.findData("zh-Hans")
                    scope.language_combo.setCurrentIndex(language_index)
                    app.processEvents()
                    detail["translated_summary"] = summary.text()
                    assert "2 个 XHTML" in summary.text()
                    assert config.combo.currentData() == "t2jp"
                    assert nav_item.checkState() == Qt.CheckState.Checked
                    dialog.grab().save(str(output_dir / "scope-settings-translated-zh-Hans.png"))
                    detail["readfile_count"] = len(adapter.reads)
                    detail["book_write_count"] = len(adapter.writes)
                    detail["backend_constructor_count"] = counts["backend_constructors"]
                    detail["profile_save_count"] = counts["profile_saves"]
                    assert detail["readfile_count"] == 0
                    assert detail["book_write_count"] == 0
                    assert detail["backend_constructor_count"] == 0
                    assert detail["profile_save_count"] == 0
                    dialog.reject()

                QTimer.singleShot(0, interact)
                dialog.exec()

            preview_window.exec_dialog = interactive_exec
            original_run_options_exec = run_options_module.exec_dialog
            run_options_module.exec_dialog = interactive_exec
            try:
                outcome = preview_window.choose_scope(
                    adapter, initial_language=language, translator=translator,
                    available_configs=("s2t", "s2tw", "t2jp"), default_config="s2t",
                    initial_options={
                        "include_nav": True, "include_ncx": True,
                        "include_metadata": True, "convert_alt": False,
                        "force_pivot": True, "pivot_chain": ("t2s", "s2t"),
                    }, services=services, metadata_available=True,
                )
            finally:
                run_options_module.exec_dialog = original_run_options_exec
                preview_window._ScopeDialog = original_scope
                preview_window._ConversionConfigDialog = original_config
            detail["cancel_keeps_outcome_unaccepted"] = not outcome.accepted
            assert detail["cancel_keeps_outcome_unaccepted"]
    finally:
        OpenCCBackend.__init__ = original_backend_init
    return detail


def _probe_state(qt, app, language, state):
    translator = Translator(language)
    adapter = MetadataAdapter()
    original_exec = preview_window.exec_dialog
    captured = {}
    original_scope = preview_window._ScopeDialog
    original_config = preview_window._ConversionConfigDialog

    def capture_scope(*args, **kwargs):
        captured["scope"] = original_scope(*args, **kwargs)
        return captured["scope"]

    def capture_config(*args, **kwargs):
        captured["config"] = original_config(*args, **kwargs)
        return captured["config"]

    preview_window._ScopeDialog = capture_scope
    preview_window._ConversionConfigDialog = capture_config
    report = {}

    def inspect_dialog(dialog):
        dialog.show()
        app.processEvents()
        report["summary"] = next(label.text() for label in dialog.findChildren(qt.QLabel)
                                 if label.text().startswith(translator.text("scope.run_summary").split("{")[0]))
        analyze_button = next(
            button for button in dialog.findChildren(qt.QPushButton)
            if button.text() == translator.text("config.continue"))
        report["analyze_enabled"] = analyze_button.isEnabled()
        dialog.reject()

    preview_window.exec_dialog = inspect_dialog
    try:
        with tempfile.TemporaryDirectory(prefix="opencc-probe-") as temporary:
            root = Path(temporary)
            services = RunSettings(
                SimpleNamespace(paths=SimpleNamespace(root=root, profiles=root / "profiles",
                                                      rules=root / "rules")),
                adapter, {}, language=language, session_id="probe")
            preview_window.choose_scope(
                adapter, initial_language=language, translator=translator,
                available_configs=("s2t", "s2t_jieba"), default_config="s2t_jieba",
                jieba_probe=Probe(state), services=services,
            )
    finally:
        preview_window.exec_dialog = original_exec
        preview_window._ScopeDialog = original_scope
        preview_window._ConversionConfigDialog = original_config
    if state == "available":
        assert report["analyze_enabled"]
        assert translator.text("config.jieba") in report["summary"]
        assert captured["config"].jieba_checkbox.isChecked()
    else:
        assert not report["analyze_enabled"]
        expected = ("config.jieba_checking" if state == "pending"
                    else "config.jieba_reselect")
        assert translator.text(expected) in captured["config"].jieba_status.text()
        assert translator.text(expected) not in report["summary"]
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--language", default="en")
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=640)
    options = parser.parse_args()
    options.output.mkdir(parents=True, exist_ok=True)
    qt = load_qt()
    app = ensure_application(qt, language=options.language)
    result = {
        "PySide6": PySide6.__version__, "python": platform.python_version(),
        "platform": platform.platform(), "qpa_platform": os.environ.get("QT_QPA_PLATFORM"),
        "screen_geometry": [app.primaryScreen().geometry().width(),
                            app.primaryScreen().geometry().height()],
        "screen_device_pixel_ratio": app.primaryScreen().devicePixelRatio(),
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "language": options.language, "requested_window": [options.width, options.height],
        "merged_scope_settings": _run_summary(
            qt, app, options.language, options.output, options.width, options.height),
        "jieba_pending": _probe_state(qt, app, options.language, "pending"),
        "jieba_unavailable": _probe_state(qt, app, options.language, "unavailable"),
        "jieba_available": _probe_state(qt, app, options.language, "available"),
    }
    (options.output / f"summary-{options.language}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
