"""S3: an exception from the post-preview progress UI inside the write loop is reported as 'no files written'."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)
import tempfile
import json
from pathlib import Path

import ui.preview_window as pw
from app.controller import Controller
from core.preview import PreviewSession
from sigil.scope import Scope, TargetSelection
from ui.preview_window import PreviewOutcome, ScopeOutcome


class Book:
    def __init__(self):
        self.files = {"a": "<p>汉字</p>", "b": "<p>汉字</p>"}
        self.writes = []

    def text_iter(self):
        for k in self.files:
            yield k, f"Text/{k}.xhtml"

    def readfile(self, i):
        return self.files[i]

    def writefile(self, i, d):
        self.writes.append(i)


class Progress:
    def __init__(self, post):
        self.post = post

    def disable_cancel(self):
        pass

    def update(self, phase, index, total, href):
        if self.post and phase == "committing" and index == 1:
            raise RuntimeError("Internal C++ object (QProgressDialog) already deleted")

    def cancelled(self):
        return False

    def close(self):
        pass


reporters = []


def create(*a, **k):
    r = Progress(post=bool(reporters))
    reporters.append(r)
    return r


def accept_all(planned, **k):
    ps = tuple(PreviewSession(i.plan) for i in planned)
    for p in ps:
        p.accept_all()
    return PreviewOutcome(True, ps)


errors = []
results = []
pw.choose_scope = lambda adapter, initial_language, **k: ScopeOutcome(
    True, TargetSelection(Scope.ALL_XHTML, ("a", "b")), initial_language
)
pw.choose_conversion_config = lambda *a, **k: "s2t"
pw.show_preview = accept_all
pw.create_progress_reporter = create
pw.show_result = lambda **k: results.append(k)
pw.show_error = lambda **k: errors.append(k)
book = Book()
with tempfile.TemporaryDirectory() as d:
    c = Controller(book, data_dir=Path(d))
    try:
        c.run()
        print("returned normally")
    except Exception as exc:
        print("raised", type(exc).__name__)
    summary = json.loads(c.logger.summary_path.read_text())
print("book.writes =", book.writes)
print("show_error files_written =", errors[0]["files_written"], "kind =", errors[0]["kind"])
print("show_result calls =", results)
print("summary status/files_changed =", summary["status"], summary["files_changed"])
