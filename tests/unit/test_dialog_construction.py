from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from core.models import ConversionPlan, SourceSpan, TokenChange
from core.preview import PreviewSession
from rules.store import RuleSet
from sigil.scope import Scope, TextFile
from tests.support import fake_qt
from ui.history_window import show_history
from ui.i18n import Translator
from ui.preview_window import (
    _PreviewDialog,
    _ScopeDialog,
    choose_conversion_config,
)
from ui.profile_window import ProfileManagerDialog
from ui.rules_window import RuleManagerDialog


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
    )

    assert dialog.analyze_button.isEnabled()
    assert dialog.selected_ids() == ("a",)
    assert [dialog.list_widget.item(i).data(qt.Qt.CheckStateRole) for i in range(3)] == [
        None,
        None,
        None,
    ]

    dialog.list_widget.setCurrentRow(1)
    assert dialog.analyze_button.isEnabled()
    assert dialog.selected_ids() == ("b",)

    dialog.all_radio.setChecked(True)
    dialog.single_radio.setChecked(True)
    assert dialog.analyze_button.isEnabled()
    assert dialog.selected_ids() == ("b",)


def test_conversion_profile_rule_and_history_dialogs_construct(monkeypatch, tmp_path):
    qt = fake_qt.make()
    monkeypatch.setattr("ui.preview_window._load_ui_qt", lambda _translator: qt)
    outcome = choose_conversion_config(("s2t",), translator=Translator("en"))
    assert outcome.action == "cancel"

    profile_dialog = ProfileManagerDialog(
        fake_qt.make(), (), translator=Translator("en"), available_configs=("s2t",)
    )
    assert profile_dialog.dialog is not None

    rule_dialog = RuleManagerDialog(
        fake_qt.make(), (), translator=Translator("en"), rulesets=(RuleSet("default"),)
    )
    assert rule_dialog.dialog is not None

    history = show_history(
        tmp_path / "history",
        qt_widgets=fake_qt.make(),
        translator=Translator("en"),
    )
    assert history is not None
    assert history.history_table.rowCount() == 0


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
    ui_root = Path("plugin/OpenCCForSigil/ui")
    failures: list[str] = []
    for path in sorted(ui_root.glob("*.py")):
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
