# ruff: noqa: E401, E402, E701, E702, E731, F401, F811, F841
"""FIX-01: RuleConflictError escapes _ConversionConfigDialog._accept (fake Qt).

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
from app.profiles import Profile
from rules.models import Rule
from rules.store import RuleSet
from opencc_backend.configs import V1_CONFIGS
from tests.support.fake_qt import make as make_fake_qt
from ui.i18n import Translator
from ui.preview_window import _ConversionConfigDialog

with TemporaryDirectory() as d:
    root = Path(d)
    storage = SimpleNamespace(paths=SimpleNamespace(root=root, profiles=root/"profiles", rules=root/"rules"))
    settings = RunSettings(storage, SimpleNamespace(), {}, language="en", session_id="x")
    settings.rules.save(RuleSet("A", (Rule(id="a1", source="软件", target="軟體", direction="s2t"),)))
    settings.rules.save(RuleSet("B", (Rule(id="b1", source="软件", target="軟件", direction="s2t"),)))
    settings.active = replace(settings.active, ruleset_ids=("A", "B"), builtin_rules_enabled=False)
    shown = []
    import ui.preview_window as pw
    pw.show_error_details = lambda *a, **k: shown.append(a[3])
    dialog = _ConversionConfigDialog(make_fake_qt(), tuple(V1_CONFIGS), "s2t", {},
                                     translator=Translator("en"), services=settings)
    try:
        dialog._accept()
        print("accept returned; accepted=", dialog.accepted, "shown=", shown)
    except Exception as exc:
        print("EXCEPTION escapes _accept:", type(exc).__name__, exc, "| is ValueError:", isinstance(exc, ValueError))
