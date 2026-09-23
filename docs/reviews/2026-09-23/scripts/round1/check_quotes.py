"""Round 1 (L-01): quotation pairing across inline tags and user-rule spans.

Baseline b2f674b printed ``「他說<em>你好</em>「`` and ``「软件「``; after the fix
both closing marks must be ``」``.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)

from core.models import ConvertRequest, RuleSnapshot as CoreSnapshot
from core.staging import apply_changes
from core.workflow import ConversionWorkflow
from opencc_backend.backend import OpenCCBackend
from rules.models import Rule, RuleSnapshot
from sigil.adapter import SigilBookAdapter
from sigil.scope import Scope, TargetSelection


class Book:
    """Minimal BookContainer: text_iter/readfile/writefile only."""

    def __init__(self, files):
        self.files = files

    def text_iter(self):
        for file_id in self.files:
            yield file_id, f"Text/{file_id}.xhtml"

    def readfile(self, file_id):
        return self.files[file_id]

    def writefile(self, file_id, data):
        self.files[file_id] = data


def plan_single(source, request):
    backend = OpenCCBackend(request.config)
    try:
        workflow = ConversionWorkflow(
            SigilBookAdapter(Book({"a": source})),
            backend,
            request,
            targets=TargetSelection(Scope.SINGLE, ("a",)),
        )
        return workflow.plan()[0].plan
    finally:
        backend.close()


def run(source, rules=()):
    snapshot = RuleSnapshot.freeze(rules)
    request = ConvertRequest(
        "s2t",
        quotation_mode="corner",
        rules_snapshot=(
            CoreSnapshot(rules_hash=snapshot.sha256, rules=snapshot.rules)
            if rules
            else CoreSnapshot()
        ),
    )
    plan = plan_single(source, request)
    print(repr(source), "->", repr(apply_changes(source, plan.changes)))


if __name__ == "__main__":
    run('<p>"他说<em>你好</em>"</p>')
    run('<p>"软件"</p>', rules=(Rule(id="p1", type="protect", direction="s2t", source="软件"),))
    run('<p>"软件"</p>')
