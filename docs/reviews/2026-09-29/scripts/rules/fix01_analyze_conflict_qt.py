# ruff: noqa: E401, E402, E701, E702, E731, F401, F811, F841
"""FIX-01: clicking Analyze with a cross-ruleset conflict does nothing (real Qt).

Run from the repository root. Read-only: uses temporary directories, never the user's data.
"""
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))
sys.path.insert(0, str(REPO))

import sys
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from dataclasses import replace
from app.settings import RunSettings
from rules.models import Rule
from rules.store import RuleSet
from opencc_backend.configs import V1_CONFIGS
from ui.i18n import Translator
from ui.qt import load_qt, ensure_application
import ui.preview_window as pw

qt = load_qt(); app = ensure_application(qt, language="en")
boxes = []
qt.QMessageBox.warning = staticmethod(lambda *a, **k: boxes.append(("warning", a[2] if len(a) > 2 else a)))
qt.QMessageBox.critical = staticmethod(lambda *a, **k: boxes.append(("critical", a)))
qt.QMessageBox.information = staticmethod(lambda *a, **k: boxes.append(("information", a)))
# show_error_details() opens a modal QMessageBox via exec(); record it instead so the
# script cannot block offscreen once FIX-01 routes the conflict to that helper.
pw.show_error_details = lambda _qt, _parent, _title, summary, _detail: boxes.append(
    ("error_details", summary))
with TemporaryDirectory() as d:
    root = Path(d)
    storage = SimpleNamespace(paths=SimpleNamespace(root=root, profiles=root/"profiles", rules=root/"rules"))
    settings = RunSettings(storage, SimpleNamespace(), {}, language="en", session_id="x")
    settings.rules.save(RuleSet("A", (Rule(id="a1", source="软件", target="軟體", direction="s2t"),)))
    settings.rules.save(RuleSet("B", (Rule(id="b1", source="软件", target="軟件", direction="s2t"),)))
    settings.active = replace(settings.active, ruleset_ids=("A", "B"), builtin_rules_enabled=False)
    dialog = pw._ConversionConfigDialog(qt, tuple(V1_CONFIGS), "s2t", {}, translator=Translator("en"), services=settings)
    dialog.dialog.show()
    dialog.continue_button.click()   # real Qt signal emission
    app.processEvents()
    print("after click: accepted =", dialog.accepted, "| dialog visible =", dialog.dialog.isVisible(), "| message boxes =", boxes)
