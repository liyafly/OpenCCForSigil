"""S6: stale in-memory preferences overwrite values saved during the same run."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)
import tempfile
import json
from pathlib import Path

import ui.preview_window as pw
from app.controller import Controller
from sigil.scope import Scope, TargetSelection
from ui.preview_window import ScopeOutcome


class Book:
    def text_iter(self):
        yield "a", "Text/a.xhtml"

    def readfile(self, i):
        return "<p>汉字</p>"

    def writefile(self, i, d):
        raise AssertionError


def choose_scope(adapter, initial_language, hide_checkpoint_notice=None, **kw):
    hide_checkpoint_notice()  # user ticks "don't show again" on the banner
    return ScopeOutcome(True, TargetSelection(Scope.SINGLE, ("a",)), initial_language)


def choose_config(available, *, save_ui_preferences, **kw):
    save_ui_preferences(
        {"run_options_advanced_expanded": True, "conversion_dialog_size": [800, 600]}
    )
    return None  # user presses Cancel


pw.choose_scope = choose_scope
pw.choose_conversion_config = choose_config
with tempfile.TemporaryDirectory() as d:
    rc = Controller(Book(), data_dir=Path(d)).run()
    prefs = json.loads((Path(d) / "preferences.json").read_text())
print("rc", rc, "checkpoint_notice:", prefs.get("checkpoint_notice"), "ui:", prefs.get("ui"))
