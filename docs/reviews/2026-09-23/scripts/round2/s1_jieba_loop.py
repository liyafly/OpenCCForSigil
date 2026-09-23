"""S1: after preview -> back, second settings dialog gets a stale config list and an unprobed backend."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)
import tempfile
import time
from pathlib import Path

import ui.preview_window as pw
from app.controller import Controller
from sigil.scope import Scope, TargetSelection
from ui.preview_window import PreviewOutcome, ScopeOutcome, ConfigOutcome
from ui.run_options import ConfigurationChoice


class Book:
    def __init__(self):
        self.files = {"a": "<p>汉字</p>"}
        self.writes = []

    def text_iter(self):
        yield "a", "Text/a.xhtml"

    def readfile(self, i):
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


calls = []
previews = [0]


def choose_scope(adapter, initial_language, **kw):
    return ScopeOutcome(True, TargetSelection(Scope.SINGLE, ("a",)), initial_language)


def choose_config(available, *, default_config, jieba_probe, **kw):
    # Wait until the first backend's background probe finishes, as a real user would.
    if not calls:
        while jieba_probe.jieba_probe_state()[0] == "pending":
            time.sleep(0.05)
    state = jieba_probe.jieba_probe_state()[0]
    calls.append(
        dict(
            default=default_config,
            backend=jieba_probe.config,
            state=state,
            jieba_in_list=[c for c in available if c.endswith("_jieba")],
        )
    )
    return (
        ConfigOutcome("continue", ConfigurationChoice("s2t_jieba", {})) if len(calls) == 1 else None
    )


def show_preview(planned, **kw):
    previews[0] += 1
    return PreviewOutcome(False, (), back_to_settings=True)


pw.choose_scope = choose_scope
pw.choose_conversion_config = choose_config
pw.show_preview = show_preview
pw.create_progress_reporter = lambda *a, **k: NoProgress()
pw.show_result = lambda **k: None
pw.show_error = lambda **k: print("ERROR", k)
with tempfile.TemporaryDirectory() as d:
    rc = Controller(Book(), data_dir=Path(d)).run()
print("rc", rc)
for c in calls:
    print(c)

# Now feed the second-call inputs into the real dialog state machine (fake widgets from tests).
from test_conversion_dialog_jieba import _dialog, Probe
from opencc_backend.configs import JIEBA_CONFIG_BY_BASE

probe = Probe("not_started")
dlg = _dialog(probe)
dlg._jieba_configs = {
    b: p for b, p in JIEBA_CONFIG_BY_BASE.items() if p in calls[1]["jieba_in_list"]
}
dlg.jieba_checkbox.setChecked(False)
dlg._poll_jieba_probe()
print(
    "dialog#2: status=%r checkbox_enabled=%s continue_enabled=%s resolved_config=%s"
    % (
        dlg.jieba_status.text,
        dlg.jieba_checkbox.enabled,
        dlg.continue_button.enabled,
        dlg._get_config(),
    )
)
