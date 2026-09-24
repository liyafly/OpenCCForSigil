"""Shared helpers for the round-3 repro scripts (no Qt).

Import ``common`` first: it loads ``_env`` (import paths, working directory)
and arms a 90-second watchdog, so a hang prints a stack instead of blocking.
"""

from __future__ import annotations

import faulthandler
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401

from core.models import ConvertRequest, RuleSnapshot
from core.preview import PreviewSession
from core.workflow import ConversionWorkflow
from opencc_backend.backend import OpenCCBackend
from rules.models import RuleSnapshot as FrozenRules
from sigil.adapter import SigilBookAdapter
from sigil.scope import Scope, TargetSelection

faulthandler.dump_traceback_later(90, exit=True)

XHTML = '<html xmlns="http://www.w3.org/1999/xhtml"><body>{}</body></html>'


class Book:
    """Minimal in-memory stand-in for Sigil's ``bk`` object."""

    def __init__(self, files):
        self.files = files if isinstance(files, dict) else {"a": files}
        self.writes = []

    def text_iter(self):
        for file_id in self.files:
            yield file_id, f"{file_id}.xhtml"

    def readfile(self, file_id):
        return self.files[file_id]

    def writefile(self, file_id, value):
        self.writes.append((file_id, value))
        self.files[file_id] = value


_BACKENDS = {}


def backend(config):
    if config not in _BACKENDS:
        _BACKENDS[config] = OpenCCBackend(config)
    return _BACKENDS[config]


def request(config="s2t", *, rules=(), quotation_mode="keep", detailed=False, diag=False):
    frozen = FrozenRules.freeze(rules)
    return ConvertRequest(
        config,
        rules_snapshot=RuleSnapshot(rules_hash=frozen.sha256, rules=frozen.rules),
        quotation_mode=quotation_mode,
        detailed_classification=detailed,
        diagnose_mixed=diag,
    )


def run(source, *, rules=(), config="s2t", quotation_mode="keep", commit=True,
        detailed=False, diag=False, tokenizer_options=None):
    """Plan, accept everything, stage, verify and (optionally) commit."""

    book = Book(source)
    scope = Scope.SINGLE if len(book.files) == 1 else Scope.ALL_XHTML
    workflow = ConversionWorkflow(
        SigilBookAdapter(book), backend(config),
        request(config, rules=rules, quotation_mode=quotation_mode,
                detailed=detailed, diag=diag),
        targets=TargetSelection(scope, tuple(book.files)),
        tokenizer_options=tokenizer_options,
    )
    planned = workflow.plan()
    previews = [PreviewSession(item.plan) for item in planned]
    for preview in previews:
        preview.accept_all()
    staged = workflow.stage(workflow.finalize(previews))
    workflow.verify(staged)
    if commit:
        workflow.commit(staged)
    return book, workflow, planned, staged
