from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from core.models import ConversionPlan, SourceSpan, TokenChange
from core.preview import PreviewSession
from rules.store import RuleSet
from sigil.scope import Scope, TextFile
from tests.support import fake_qt
from ui import preview_window, rules_window
from ui.history_window import show_history
from ui.i18n import Translator
from ui.preview_window import (
    _PreviewDialog,
    _ScopeDialog,
)
from ui.profile_window import ProfileManagerDialog
from ui.rules_window import RuleManagerDialog

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _preview_inputs():
    change = TokenChange(
        source="后",
        target="後",
        span=SourceSpan(0, 1),
        rule_source="OpenCC:s2t",
        change_id="change-1",
        file_id="chapter",
        category="character",
        risk="LOW",
    )
    preview = PreviewSession(
        ConversionPlan(source_sha256="source-hash", file_id="chapter", changes=(change,))
    )
    planned = (
        SimpleNamespace(
            source=SimpleNamespace(
                file_id="chapter", href="Text/chapter.xhtml", document_kind="xhtml"
            ),
            plan=preview.plan,
        ),
    )
    return planned, (preview,)


def test_scope_flow_has_no_standalone_conversion_config_entrypoint():
    obsolete_entrypoint = "choose_" + "conversion_config"
    assert not hasattr(preview_window, obsolete_entrypoint)

def test_preview_dialog_constructs_with_and_without_export_service():
    planned, previews = _preview_inputs()

    no_service = _PreviewDialog(
        fake_qt.make_with_table(), planned, previews, Translator("en"), None
    )
    assert not no_service.export_button.isEnabled()

    service = SimpleNamespace(export_preview=lambda *_args: None)
    with_service = _PreviewDialog(
        fake_qt.make_with_table(), planned, previews, Translator("en"), service
    )
    assert with_service.export_button.isEnabled()


def test_scope_dialog_constructs_and_single_file_can_continue_after_row_change():
    qt = fake_qt.make()
    inventory = (
        TextFile("a", "Text/a.xhtml"),
        TextFile("b", "Text/b.xhtml"),
        TextFile("c", "Text/c.xhtml"),
    )
    dialog = _ScopeDialog(
        qt,
        inventory,
        ("a",),
        "en",
        Translator("en"),
        initial_scope=Scope.SINGLE,
        embedded=True,
    )

    assert not hasattr(dialog, "analyze_button")
    assert not hasattr(dialog, "single_radio")
    assert dialog.selected_radio.isChecked()
    assert dialog._selection_is_valid()
    assert dialog.selected_ids() == ("a",)
    assert [dialog.list_widget.item(i).checkState() for i in range(3)] == [
        qt.Qt.Checked,
        qt.Qt.Unchecked,
        qt.Qt.Unchecked,
    ]

    dialog.list_widget.setCurrentRow(1)
    assert dialog._selection_is_valid()
    assert dialog.selected_ids() == ("a",)
    dialog.list_widget.item(1).setCheckState(qt.Qt.Checked)
    assert dialog.selected_ids() == ("a", "b")
    dialog.all_radio.setChecked(True)
    assert dialog._selection_is_valid()
    dialog.selected_radio.setChecked(True)
    dialog._accept(close=False)
    assert dialog.selection.scope is Scope.SELECTED
    assert dialog.selection.file_ids == ("a", "b")


def test_scope_and_conversion_configuration_share_one_dialog(monkeypatch):
    qt = fake_qt.make()
    monkeypatch.setattr(preview_window, "_load_ui_qt", lambda _translator: qt)
    monkeypatch.setattr(preview_window, "ensure_application", lambda *_args, **_kwargs: None)
    executed = []

    class Adapter:
        def text_file_inventory(self):
            return (TextFile("chapter", "Text/chapter.xhtml"),)

        def selected_ids(self):
            return ("chapter",)

        def text_files(self, scope):
            assert scope is Scope.SPINE
            return (("chapter", "Text/chapter.xhtml"),)

        def nav_id(self):
            return None

    def execute(dialog):
        executed.append(dialog)
        summary, direction_row, tabs, footer = dialog._layout.children
        assert isinstance(tabs, qt.QTabWidget)
        language_corner = tabs.cornerWidget()
        assert isinstance(language_corner, qt.QWidget)
        assert language_corner._layout.children[0].text() == "Interface language"
        assert isinstance(language_corner._layout.children[1], qt.QComboBox)
        assert language_corner._layout.children[1].currentData() == "en"
        assert ("setCornerWidget", (language_corner, qt.Qt.TopRightCorner)) in tabs.calls
        assert summary.text().startswith("This run: 1 XHTML")
        assert direction_row.children[0].text() == "Conversion direction"
        assert direction_row.children[1].currentData() == "s2t"
        assert sum(name == "addTab" for name, _args in tabs.calls) == 2
        assert footer.children[-1].text() == "Analyze and preview"
        assert dialog.windowTitle() == "OpenCCForSigil — Chinese conversion"
        footer.children[-1].click()

    monkeypatch.setattr(preview_window, "exec_dialog", execute)
    outcome = preview_window.choose_scope(
        Adapter(), initial_language="en", translator=Translator("en"),
        available_configs=("s2t",),
    )

    assert len(executed) == 1
    assert outcome.accepted is True
    assert outcome.selection.file_ids == ("chapter",)
    assert str(outcome.configuration) == "s2t"


def test_merged_dialog_language_change_keeps_analyze_label(monkeypatch):
    qt = fake_qt.make()
    monkeypatch.setattr(preview_window, "_load_ui_qt", lambda _translator: qt)
    monkeypatch.setattr(preview_window, "ensure_application", lambda *_args, **_kwargs: None)
    captured = {}
    original_scope_init = preview_window._ScopeDialog.__init__
    original_config_init = preview_window._ConversionConfigDialog.__init__

    def capture_scope_init(self, *args, **kwargs):
        original_scope_init(self, *args, **kwargs)
        captured["scope"] = self

    def capture_config_init(self, *args, **kwargs):
        original_config_init(self, *args, **kwargs)
        captured["config"] = self
        captured["config_page"] = kwargs["container"]

    monkeypatch.setattr(preview_window._ScopeDialog, "__init__", capture_scope_init)
    monkeypatch.setattr(
        preview_window._ConversionConfigDialog, "__init__", capture_config_init)
    translator = Translator("en")

    class Adapter:
        def text_file_inventory(self):
            return (TextFile("chapter", "Text/chapter.xhtml"),)

        def selected_ids(self):
            return ("chapter",)

        def text_files(self, scope):
            assert scope is Scope.SPINE
            return (("chapter", "Text/chapter.xhtml"),)

        def nav_id(self):
            return None

    def execute(dialog):
        summary, direction_row, _tabs, footer = dialog._layout.children
        analyze_button = footer.children[-1]
        scope = captured["scope"]
        config = captured["config"]
        assert config.combo not in captured["config_page"]._layout.children
        assert config.direction_label not in captured["config_page"]._layout.children
        assert direction_row.children[1] is config.combo

        scope.language_combo.setCurrentIndex(scope.language_combo.findData("zh-Hans"))

        assert dialog.windowTitle() == "OpenCCForSigil — 简繁转换"
        assert direction_row.children[0].text() == translator.text("config.direction")
        assert config.combo.currentText() == translator.text("config.s2t")
        assert analyze_button.text() == translator.text("config.continue")

        config.combo.setCurrentIndex(config.combo.findData("t2s"))
        assert "繁体中文 → 简体中文" in summary.text()
        assert analyze_button.text() == translator.text("config.continue")
        analyze_button.click()

    monkeypatch.setattr(preview_window, "exec_dialog", execute)
    outcome = preview_window.choose_scope(
        Adapter(), initial_language="en", translator=translator,
        available_configs=("s2t", "t2s"),
    )

    assert outcome.accepted is True
    assert str(outcome.configuration) == "t2s"


def test_conversion_profile_rule_and_history_dialogs_construct(monkeypatch, tmp_path):
    qt = fake_qt.make()
    monkeypatch.setattr("ui.preview_window._load_ui_qt", lambda _translator: qt)

    profile_dialog = ProfileManagerDialog(
        fake_qt.make(),
        (),
        translator=Translator("en"),
        available_configs=("s2t",),
        ui_preferences={"profile_dialog_size": [910, 610]},
    )
    assert profile_dialog.dialog is not None
    assert (profile_dialog.dialog.width(), profile_dialog.dialog.height()) == (910, 610)
    assert profile_dialog.dialog.windowTitle() == "OpenCCForSigil — Profiles"
    assert profile_dialog.dialog._layout.children[-1].children == [
        profile_dialog.rename_button,
        profile_dialog.copy_button,
        profile_dialog.delete_button,
        "<stretch>",
        profile_dialog.close_button,
        profile_dialog.use_button,
    ]
    assert not hasattr(profile_dialog, "jieba_notice")
    assert not hasattr(profile_dialog, "from_current_button")

    rule_dialog = RuleManagerDialog(
        fake_qt.make(),
        (),
        translator=Translator("en"),
        rulesets=(RuleSet("default"),),
        ui_preferences={"rules_dialog_size": [930, 640]},
    )
    assert rule_dialog.dialog is not None
    assert (rule_dialog.dialog.width(), rule_dialog.dialog.height()) == (930, 640)
    assert rule_dialog.dialog.windowTitle() == "OpenCCForSigil — Rules"
    assert not hasattr(rule_dialog, "jieba_notice")

    history = show_history(
        tmp_path / "history",
        qt_widgets=fake_qt.make(),
        translator=Translator("en"),
        ui_preferences={"history_dialog_size": [1020, 610]},
    )
    assert history is not None
    assert (history.width(), history.height()) == (1020, 610)
    assert history.windowTitle() == "OpenCCForSigil — Conversion history"
    assert history.history_table.rowCount() == 0


def test_error_report_dialog_constructs_after_dictionary_inspector_removal(monkeypatch):
    qt = fake_qt.make_with_table()
    monkeypatch.setattr(preview_window, "_load_ui_qt", lambda _translator: qt)
    monkeypatch.setattr(preview_window, "exec_dialog", lambda _dialog: None)
    preview_window.show_error(
        kind="VERIFY_FAILED",
        detail="verification failed",
        files_written=0,
        log_path="/tmp/session.jsonl",
    )
    preview_window._show_report_text(qt, "report details", Translator("en"))

    assert not hasattr(rules_window, "show_dictionary_inspector")


def _class_methods(node: ast.ClassDef, classes: dict[str, ast.ClassDef]) -> set[str]:
    methods = {
        child.name
        for child in node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id in classes:
            methods.update(_class_methods(classes[base.id], classes))
    return methods


def test_ui_self_method_calls_resolve_in_the_class_or_its_local_bases():
    ui_root = REPOSITORY_ROOT / "plugin" / "OpenCCForSigil" / "ui"
    files = tuple(sorted(ui_root.glob("*.py")))
    assert files, f"no UI source files found under {ui_root}"
    failures: list[str] = []
    for path in files:
        module = ast.parse(path.read_text(encoding="utf-8"))
        classes = {node.name: node for node in ast.walk(module) if isinstance(node, ast.ClassDef)}
        for node in classes.values():
            # Qt subclasses may call inherited methods that are not declared here.
            has_external_base = any(
                not isinstance(base, ast.Name) or base.id not in classes
                for base in node.bases
            )
            methods = _class_methods(node, classes)
            assigned = {
                child.attr
                for child in ast.walk(node)
                if (
                    isinstance(child, ast.Attribute)
                    and isinstance(child.value, ast.Name)
                    and child.value.id in {"self", "_self"}
                    and isinstance(child.ctx, ast.Store)
                )
            }
            if any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "setattr"
                for child in ast.walk(node)
            ):
                assigned.add("<dynamic>")
            if has_external_base:
                continue
            for call in ast.walk(node):
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == "self"
                    and call.func.attr not in methods
                    and call.func.attr not in assigned
                ):
                    failures.append(f"{path}:{call.lineno}: {node.name}.self.{call.func.attr}")

    assert not failures, "\n".join(failures)


def test_backend_self_attribute_reads_resolve_in_package_classes():
    backend_root = REPOSITORY_ROOT / "plugin" / "OpenCCForSigil" / "opencc_backend"
    files = tuple(sorted(backend_root.rglob("*.py")))
    assert files, f"no backend source files found under {backend_root}"
    failures: list[str] = []
    for path in files:
        module = ast.parse(path.read_text(encoding="utf-8"))
        classes = {node.name: node for node in ast.walk(module) if isinstance(node, ast.ClassDef)}
        for node in classes.values():
            has_external_base = any(
                not isinstance(base, ast.Name) or base.id not in classes
                for base in node.bases
            )
            if has_external_base:
                continue
            defined = _class_methods(node, classes)
            defined.update(
                child.target.id
                for child in node.body
                if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name)
            )
            defined.update(
                child.attr
                for child in ast.walk(node)
                if (
                    isinstance(child, ast.Attribute)
                    and isinstance(child.value, ast.Name)
                    and child.value.id == "self"
                    and isinstance(child.ctx, ast.Store)
                )
            )
            for read in ast.walk(node):
                if (
                    isinstance(read, ast.Attribute)
                    and isinstance(read.value, ast.Name)
                    and read.value.id == "self"
                    and isinstance(read.ctx, ast.Load)
                    and read.attr not in defined
                ):
                    failures.append(f"{path}:{read.lineno}: {node.name}.self.{read.attr}")

    assert not failures, "\n".join(failures)
