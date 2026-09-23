import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)

from core.models import ConvertRequest, RuleSnapshot
from core.preview import PreviewSession
from core.workflow import ConversionWorkflow
from opencc_backend.backend import OpenCCBackend
from rules.models import RuleSnapshot as Rules
from sigil.adapter import SigilBookAdapter
from sigil.scope import Scope, TargetSelection


class Book:
    def __init__(self, files):
        self.files = files if isinstance(files, dict) else {"a": files}
        self.writes = []

    def text_iter(self):
        for k in self.files:
            yield k, f"{k}.xhtml"

    def readfile(self, fid):
        return self.files[fid]

    def writefile(self, fid, s):
        self.writes.append((fid, s))


def plan(source, *, rules=(), quotation_mode="corner", config="s2t", **kw):
    frozen = Rules.freeze(rules)
    request = ConvertRequest(
        config,
        rules_snapshot=RuleSnapshot(rules_hash=frozen.sha256, rules=frozen.rules),
        quotation_mode=quotation_mode,
        detailed_classification=kw.pop("detailed", False),
        diagnose_mixed=kw.pop("diag", False),
        **kw,
    )
    book = Book(source)
    backend = OpenCCBackend(config)
    wf = ConversionWorkflow(
        SigilBookAdapter(book),
        backend,
        request,
        targets=TargetSelection(
            Scope.SINGLE if len(book.files) == 1 else Scope.ALL_XHTML, tuple(book.files)
        ),
    )
    planned = wf.plan()
    backend.close()
    return book, wf, planned


def stage_all(wf, planned):
    previews = [PreviewSession(p.plan) for p in planned]
    for p in previews:
        p.accept_all()
    staged = wf.stage(wf.finalize(previews))
    return staged, wf.verify(staged)
