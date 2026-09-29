"""Read-only UX simplicity probe (real PySide6, synthetic data, temp storage).

Measures first-screen control counts, default tab/focus, button labels,
Enter/Esc semantics and tab order for the merged settings dialog, preview,
rules, and profile windows. Writes JSON + screenshots to --output.
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "plugin/OpenCCForSigil"))

from PySide6.QtCore import QTimer, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from app.profiles import Profile  # noqa: E402
from app.settings import RunSettings, profile_options  # noqa: E402
from core.models import ConversionPlan, SourceSpan, TokenChange  # noqa: E402
from core.preview import PreviewSession  # noqa: E402
from sigil.scope import TextFile  # noqa: E402
from sigil.storage import UserDataStore  # noqa: E402
from ui import preview_window  # noqa: E402
from ui.i18n import Translator  # noqa: E402
from ui.profile_window import ProfileManagerDialog  # noqa: E402
from ui.qt import ensure_application, load_qt  # noqa: E402
from ui.rules_window import RuleManagerDialog  # noqa: E402
from rules.models import Rule  # noqa: E402

INTERACTIVE = ("QPushButton", "QToolButton", "QCheckBox", "QRadioButton", "QComboBox",
               "QLineEdit", "QSpinBox", "QPlainTextEdit", "QListWidget", "QTableView",
               "QTableWidget", "QTabBar")


def visible_controls(qt, root):
    counts = {}
    labels = []
    for name in INTERACTIVE:
        kind = getattr(qt, name)
        for widget in root.findChildren(kind):
            if not widget.isVisibleTo(root):
                continue
            if name == "QToolButton" and widget.parent() is not None and \
                    type(widget.parent()).__name__ in {"QTabBar", "QScrollBar"}:
                continue
            counts[name] = counts.get(name, 0) + 1
            text = getattr(widget, "text", None)
            text = text() if callable(text) and name not in {"QPlainTextEdit", "QLineEdit"} else ""
            if name in {"QPushButton", "QToolButton", "QCheckBox", "QRadioButton"}:
                labels.append(f"{name}:{text}|enabled={widget.isEnabled()}")
    counts["total_clickable"] = sum(counts.get(k, 0) for k in (
        "QPushButton", "QToolButton", "QCheckBox", "QRadioButton", "QComboBox"))
    return counts, labels


def focus_chain(root, limit=40):
    chain = []
    start = root.focusWidget() or root
    widget = start.nextInFocusChain()
    seen = 0
    while widget is not None and widget is not start and seen < limit:
        if widget.isVisible() and widget.isEnabled() and widget.focusPolicy() & Qt.TabFocus:
            text = getattr(widget, "text", None)
            text = text() if callable(text) and type(widget).__name__ not in {
                "QPlainTextEdit", "QLineEdit"} else ""
            chain.append(f"{type(widget).__name__}:{text}")
        widget = widget.nextInFocusChain()
        seen += 1
    return chain


class Adapter:
    def __init__(self, selected=()):
        self._selected = selected

    def text_file_inventory(self):
        return tuple(TextFile(f"c{i}", f"Text/chapter{i}.xhtml") for i in range(1, 6)) + (
            TextFile("nav", "Text/nav.xhtml"),)

    def selected_ids(self):
        return self._selected

    def nav_id(self):
        return "nav"

    def text_files(self, _scope):
        return tuple((f"c{i}", f"Text/chapter{i}.xhtml") for i in range(1, 6))


def probe_merged(qt, app, language, out, selected, tag):
    tr = Translator(language)
    report = {"sigil_selection": list(selected)}
    captured = {}
    orig_scope, orig_config = preview_window._ScopeDialog, preview_window._ConversionConfigDialog
    orig_exec = preview_window.exec_dialog

    def cs(*a, **k):
        captured["scope"] = orig_scope(*a, **k)
        return captured["scope"]

    def cc(*a, **k):
        captured["config"] = orig_config(*a, **k)
        return captured["config"]

    def fake_exec(dialog):
        dialog.resize(960, 640)
        dialog.show()
        app.processEvents()
        tabs = dialog.findChild(qt.QTabWidget)
        scope = captured["scope"]
        config = captured["config"]
        buttons = [b for b in dialog.findChildren(qt.QPushButton) if b.isDefault()]
        report["window_title"] = dialog.windowTitle()
        report["initial_tab_index"] = tabs.currentIndex()
        report["initial_tab_text"] = tabs.tabText(tabs.currentIndex())
        report["default_button_text"] = [b.text() for b in buttons]
        report["default_button_enabled"] = [b.isEnabled() for b in buttons]
        report["checked_scope_radio"] = next(r.text() for r in (
        scope.selected_radio, scope.spine_radio, scope.all_radio)
            if r.isChecked())
        report["direction_default"] = config.combo.currentData()
        report["direction_count"] = sum(1 for i in range(config.combo.count())
                                        if config.combo.itemData(i))
        report["focus_widget_at_open"] = type(app.focusWidget()).__name__ if app.focusWidget() else None
        report["tab0_controls"], report["tab0_labels"] = visible_controls(qt, tabs.widget(0))
        report["outer_summary"] = next(
            (label.text() for label in dialog.findChildren(qt.QLabel)
             if label.text().startswith(tr.text("scope.run_summary").split("{")[0])), None)
        dialog.grab().save(str(out / f"merged-{tag}-{language}-tab0.png"))
        tabs.setCurrentIndex(1)
        app.processEvents()
        report["tab1_controls_collapsed"], report["tab1_labels_collapsed"] = visible_controls(
            qt, tabs.widget(1))
        dialog.grab().save(str(out / f"merged-{tag}-{language}-tab1.png"))
        config.options_panel.advanced_button.setChecked(True)
        app.processEvents()
        report["tab1_controls_expanded"], _ = visible_controls(qt, tabs.widget(1))
        config.options_panel.advanced_button.setChecked(False)
        app.processEvents()
        tools_menu = config.options_panel.tools_menu
        report["tools_menu_actions"] = [a.text() for a in tools_menu.actions()]
        # Enter inside the file filter box: does it trigger analysis?
        tabs.setCurrentIndex(0)
        app.processEvents()
        scope.filter_edit.setFocus()
        QTest.keyClicks(scope.filter_edit, "chapter")
        accepted_before = dialog.result()
        QTest.keyClick(scope.filter_edit, Qt.Key_Return)
        app.processEvents()
        report["enter_in_filter_closed_dialog"] = not dialog.isVisible()
        report["enter_in_filter_dialog_result"] = dialog.result()
        report["enter_in_filter_scope_accepted"] = scope.accepted
        report["enter_in_filter_config_accepted"] = config.accepted
        if dialog.isVisible():
            scope.filter_edit.clear()
            app.processEvents()
            report["tab_order_from_filter"] = focus_chain(dialog)
            dialog.reject()
        del accepted_before

    preview_window._ScopeDialog, preview_window._ConversionConfigDialog = cs, cc
    preview_window.exec_dialog = fake_exec
    try:
        with tempfile.TemporaryDirectory() as tmp:
            storage = UserDataStore(Path(tmp))
            storage.ensure_layout()
            adapter = Adapter(selected)
            services = RunSettings(storage, adapter, {}, language=language, session_id="ux")
            preview_window.choose_scope(
                adapter, initial_language=language, translator=tr,
                available_configs=("s2t", "t2s", "s2tw", "s2twp", "s2hk", "s2hkp", "tw2s",
                                   "tw2sp", "hk2s", "hk2sp", "t2tw", "t2hk", "tw2t", "hk2t",
                                   "t2jp", "jp2t"),
                default_config="s2t", initial_options=profile_options(services.active),
                services=services, metadata_available=True, nav_available=True,
            )
    finally:
        preview_window._ScopeDialog, preview_window._ConversionConfigDialog = orig_scope, orig_config
        preview_window.exec_dialog = orig_exec
    return report


def probe_preview(qt, app, language, out):
    tr = Translator(language)
    changes = tuple(TokenChange(
        source="软件", target="軟體", span=SourceSpan(3 + 10 * i, 5 + 10 * i),
        rule_source="OpenCC:STPhrases", change_id=f"change-{i}", file_id="chapter",
        category="phrase", risk="LOW") for i in range(40))
    plan = ConversionPlan(source_sha256="", file_id="chapter", changes=changes)
    planned = (SimpleNamespace(source=SimpleNamespace(
        file_id="chapter", href="Text/chapter.xhtml", document_kind="xhtml",
        source="<p>" + "软件xxxxxxxx" * 40 + "</p>"), plan=plan),)
    services = SimpleNamespace(export_preview=lambda *a, **k: None,
                               checkpoint_notice_enabled=lambda: True,
                               hide_checkpoint_notice=lambda: None)
    dialog = preview_window._PreviewDialog(qt, planned, (PreviewSession(plan),), tr, services)
    dialog.dialog.resize(960, 640)
    dialog.dialog.show()
    app.processEvents()
    report = {}
    report["controls"], report["labels"] = visible_controls(qt, dialog.dialog)
    report["more_menu_actions"] = [(a.text(), a.isVisible(), a.isEnabled())
                                   for a in dialog.more_menu.actions()]
    report["apply_enabled_initially"] = dialog.apply_button.isEnabled()
    report["apply_text_initially"] = dialog.apply_button.text()
    report["apply_status"] = dialog.apply_status_label.text()
    report["summary"] = dialog.summary.text()
    report["detail_text"] = dialog.detail.toPlainText()
    report["tab_order_from_table"] = focus_chain(dialog.dialog)
    dialog.dialog.grab().save(str(out / f"preview-{language}.png"))
    # Enter on table should not accept or apply
    dialog.table_view.setFocus()
    QTest.keyClick(dialog.table_view, Qt.Key_Return)
    app.processEvents()
    report["enter_on_table_visible"] = dialog.dialog.isVisible()
    report["enter_on_table_applied"] = dialog.applied
    dialog._allow_reject = True
    dialog.dialog.reject()
    return report


def probe_rules(qt, app, language, out):
    tr = Translator(language)
    rules = RuleManagerDialog(
        qt, (Rule(id="example", direction="s2t", source="软件", target="軟體"),),
        translator=tr)
    rules.dialog.resize(960, 640)
    rules.dialog.show()
    app.processEvents()
    report = {}
    report["controls_rules_tab"], report["labels_rules_tab"] = visible_controls(qt, rules.dialog)
    report["help_text"] = tr.text("rules.help")
    report["tab_names"] = [rules.tabs.tabText(i) for i in range(rules.tabs.count())]
    report["ruleset_enabled_label"] = rules.use_in_run_check.text()
    report["add_button"] = rules.add_button.text()
    report["update_button"] = rules.update_button.text()
    report["apply_button"] = rules.apply_button.text()
    rules.dialog.grab().save(str(out / f"rules-{language}.png"))
    rules.tabs.setCurrentIndex(1)
    app.processEvents()
    rules.test_scope_combo.setFocus()
    report["test_tab_order"] = focus_chain(rules.dialog, 12)
    rules.dialog.grab().save(str(out / f"rules-test-{language}.png"))
    rules._allow_reject = True
    rules.dialog.done(0)
    return report


def probe_profiles(qt, app, language, out):
    tr = Translator(language)
    profiles = (Profile(id="conservative", name=""),
                *(Profile(id=f"p{i}", name=f"Profile {i}") for i in range(3)))
    manager = ProfileManagerDialog(qt, profiles, translator=tr,
                                   available_rulesets=("default", "names"))
    manager.dialog.resize(960, 640)
    manager.dialog.show()
    app.processEvents()
    report = {}
    report["controls"], report["labels"] = visible_controls(qt, manager.dialog)
    report["default_buttons"] = [b.text() for b in manager.dialog.findChildren(qt.QPushButton)
                                 if b.isDefault() or b.autoDefault()]
    manager.search_edit.setFocus()
    QTest.keyClicks(manager.search_edit, "Profile 1")
    QTest.keyClick(manager.search_edit, Qt.Key_Return)
    app.processEvents()
    report["enter_in_search_closed"] = not manager.dialog.isVisible()
    report["enter_in_search_accepted"] = manager.accepted
    report["enter_in_search_selected"] = getattr(manager.selected, "id", None)
    manager.dialog.grab().save(str(out / f"profiles-{language}.png"))
    if manager.dialog.isVisible():
        manager.dialog.reject()
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    qt = load_qt()
    app = ensure_application(qt)
    modals = []

    def watchdog():
        for widget in app.topLevelWidgets():
            if isinstance(widget, qt.QMessageBox) and widget.isVisible():
                modals.append(widget.text())
                widget.done(0)
            elif isinstance(widget, qt.QInputDialog) and widget.isVisible():
                modals.append("QInputDialog:" + widget.labelText())
                widget.done(0)
    timer = QTimer()
    timer.timeout.connect(watchdog)
    timer.start(200)
    result = {"auto_dismissed_modals": modals,"screen": [app.primaryScreen().availableGeometry().width(),
                         app.primaryScreen().availableGeometry().height()]}
    for language in ("zh-Hans", "en"):
        result[language] = {
            "_": print("lang", language, file=sys.stderr, flush=True),
            "merged_no_selection": probe_merged(qt, app, language, args.output, (), "nosel"),
            "merged_one_selected": probe_merged(qt, app, language, args.output, ("c2",), "one"),
            "merged_two_selected": probe_merged(qt, app, language, args.output, ("c1", "c2"), "two"),
            "preview": probe_preview(qt, app, language, args.output),
            "rules": probe_rules(qt, app, language, args.output),
            "profiles": probe_profiles(qt, app, language, args.output),
        }
    text = json.dumps(result, ensure_ascii=False, indent=1)
    (args.output / "ux_probe.json").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
