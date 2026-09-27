"""Read-only UI review probes using synthetic data and temporary user storage.

This records observations, not host acceptance. Run with a real PySide6 runtime.
No EPUB or installed plugin preferences are read or changed.
"""

import argparse
import json
import platform
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "plugin/OpenCCForSigil"))

import PySide6  # noqa: E402
from PySide6.QtCore import QPoint  # noqa: E402
from app.profiles import Profile  # noqa: E402
from app.settings import RunSettings, profile_options  # noqa: E402
from core.models import ConversionPlan, SourceSpan, TokenChange  # noqa: E402
from core.preview import PreviewSession  # noqa: E402
from opencc_backend.configs import V1_CONFIGS  # noqa: E402
from rules.models import Rule  # noqa: E402
from sigil.storage import UserDataStore  # noqa: E402
from ui.i18n import Translator  # noqa: E402
from ui.preview_window import _ConversionConfigDialog, _PreviewDialog  # noqa: E402
from ui.profile_window import ProfileManagerDialog  # noqa: E402
from ui.qt import ensure_application, load_qt  # noqa: E402
from ui.rules_window import RuleManagerDialog  # noqa: E402
from ui.window_state import restore_window_size  # noqa: E402


def dimensions(widget):
    return [widget.width(), widget.height()]


def capture(dialog, app, output, name):
    dialog.show()
    app.processEvents()
    dialog.grab().save(str(output / f"{name}.png"))
    minimum = dialog.minimumSizeHint()
    return {"size": dimensions(dialog), "minimum": [minimum.width(), minimum.height()]}


def probe(qt, app, output, language, storage_root):
    tr = Translator(language)
    storage = UserDataStore(storage_root)
    storage.ensure_layout()
    services = RunSettings(
        storage, SimpleNamespace(), {}, language=language, session_id="ui-review")
    services.active = Profile(id="review", name="UI review", builtin_rules_enabled=True)
    config = _ConversionConfigDialog(
        qt, tuple(V1_CONFIGS), "s2t", {}, translator=tr, services=services,
        initial_options=profile_options(services.active),
    )
    panel = config.options_panel
    panel.checks["builtin_rules_enabled"].setChecked(False)
    actual = services.current_profile("s2t", panel.values())
    label = panel.ruleset_label.text()
    result = {
        "language": language,
        "builtin_summary": {
            "saved_profile_value": services.active.builtin_rules_enabled,
            "effective_value": actual.builtin_rules_enabled,
            "summary_text": label,
            "summary_matches_effective": tr.text("options.builtin_off") in label,
        },
    }
    result["settings"] = capture(config.dialog, app, output, f"settings-{language}")
    config.dialog.hide()

    profiles = tuple(Profile(id=f"profile-{i}", name=f"Profile {i:02d}") for i in range(30))
    manager = ProfileManagerDialog(
        qt, profiles, translator=tr, available_rulesets=tuple(f"rules-{i:02d}" for i in range(60)),
    )
    result["profiles_60_rulesets"] = capture(
        manager.dialog, app, output, f"profiles-60-{language}")
    result["profiles_60_rulesets"]["screen_available"] = dimensions(
        manager.dialog.screen().availableGeometry())
    manager.dialog.hide()

    rules = RuleManagerDialog(
        qt, (Rule(id="example", direction="s2t", source="软件", target="軟體"),),
        translator=tr,
    )
    result["rules"] = capture(rules.dialog, app, output, f"rules-{language}")
    viewport = rules.content_scroll.viewport()
    position = rules.source_edit.mapTo(viewport, QPoint(0, 0))
    result["rules"]["source_editor_visible_in_viewport"] = viewport.rect().contains(
        position) and viewport.rect().contains(
            position + QPoint(rules.source_edit.width() - 1, rules.source_edit.height() - 1))
    result["rules"]["scroll_range"] = rules.content_scroll.verticalScrollBar().maximum()
    rules.dialog.hide()

    change = TokenChange(
        source="软件", target="軟體", span=SourceSpan(3, 5),
        rule_source="UserRule:example", change_id="change-0", file_id="chapter",
        group_id="rules:occurrence-1", category="user_rule", risk="HIGH",
    )
    plan = ConversionPlan(source_sha256="", file_id="chapter", changes=(change,))
    planned = (SimpleNamespace(
        source=SimpleNamespace(file_id="chapter", href="Text/chapter.xhtml",
                               document_kind="xhtml", source="<p>软件</p>"), plan=plan),)
    preview = _PreviewDialog(qt, planned, (PreviewSession(plan),), tr)
    result["preview"] = capture(preview.dialog, app, output, f"preview-{language}")
    result["preview"]["visible_pushbuttons"] = sum(
        button.isVisible() for button in preview.dialog.findChildren(qt.QPushButton))
    result["preview"]["table_height"] = preview.table_view.height()
    preview.dialog.hide()

    restored = qt.QDialog()
    restore_window_size(restored, {"review_size": [4000, 3000]}, "review_size", (780, 500))
    result["oversized_restore_before_show"] = dimensions(restored)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    qt = load_qt()
    app = ensure_application(qt)
    with TemporaryDirectory(prefix="opencc-ui-review-") as temporary:
        report = {
            "head": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "python": platform.python_version(), "qt_binding": PySide6.__version__,
            "platform": platform.platform(), "qpa": app.platformName(),
            "results": [probe(qt, app, args.output, language, Path(temporary) / language)
                        for language in ("en", "zh-Hans", "zh-Hant")],
        }
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (args.output / "baseline.json").write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
