"""S2: back-to-scope from the settings dialog / no-change result resets the direction."""

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
from ui.preview_window import ScopeOutcome, ConfigOutcome
from ui.run_options import ConfigurationChoice


class Book:
    def __init__(self, text):
        self.files = {"a": text}
        self.writes = []
        self.reads = []

    def text_iter(self):
        yield "a", "Text/a.xhtml"

    def readfile(self, i):
        self.reads.append(i)
        return self.files[i]

    def writefile(self, i, d):
        self.writes.append(i)


class NoProgress:
    def update(self, *a):
        pass

    def cancelled(self):
        return False

    def close(self):
        pass


def run(case):
    defaults = []
    results = []

    def choose_scope(adapter, initial_language, **kw):
        return ScopeOutcome(True, TargetSelection(Scope.SINGLE, ("a",)), initial_language)

    def choose_config(available, *, default_config, initial_options, **kw):
        defaults.append((default_config, initial_options.get("quotation_mode")))
        if len(defaults) == 1:
            choice = ConfigurationChoice("s2tw", {"quotation_mode": "corner"})
            return (
                ConfigOutcome("back_to_scope", choice)
                if case == "config_back"
                else ConfigOutcome("continue", choice)
            )
        return None  # cancel on second dialog

    def show_result(**k):
        results.append(k.get("status"))
        return "back_to_scope" if k.get("return_to_scope") else None

    pw.choose_scope = choose_scope
    pw.choose_conversion_config = choose_config
    pw.show_preview = lambda *a, **k: (_ for _ in ()).throw(AssertionError("preview"))
    pw.create_progress_reporter = lambda *a, **k: NoProgress()
    pw.show_result = show_result
    with tempfile.TemporaryDirectory() as d:
        # already-traditional text => zero changes under s2tw
        book = Book("<p>漢字</p>")
        rc = Controller(book, data_dir=Path(d)).run()
        prefs = json.loads((Path(d) / "preferences.json").read_text())
    print(
        case,
        "rc",
        rc,
        "dialog defaults:",
        defaults,
        "saved last_conversion_config:",
        prefs.get("last_conversion_config"),
        "writes",
        book.writes,
    )


run("config_back")
run("noop_back")
