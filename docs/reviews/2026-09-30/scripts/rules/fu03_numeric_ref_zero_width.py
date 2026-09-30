# ruff: noqa: E402
"""FU-03: zero-width regex skips inside a decoded numeric reference produce no diagnostic.

Run from the repository root. Read-only: uses an in-memory book.
"""
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))
sys.path.insert(0, str(REPO))

from core.workflow import ConversionWorkflow
from document.tokenizer import TokenizerOptions
from sigil.adapter import SigilBookAdapter
from tests.unit.test_regex_rules import _Backend, _Book, _request, _rule

rule = _rule(id="z", source=r"(?<=中)[^」]*", target="…")
for label, body in (("literal", "<p>中</p>"), ("numeric-ref", "<p>&#x4E2D;</p>")):
    source = "<html><body>" + body + "</body></html>"
    planned = ConversionWorkflow(
        SigilBookAdapter(_Book({"c": source})), _Backend(), _request((rule,)),
        tokenizer_options=TokenizerOptions(decode_numeric_cjk_refs=True)).plan()
    diagnostics = [(d.code, d.message) for item in planned for d in item.plan.diagnostics
                   if d.code == "REGEX_ZERO_WIDTH_SKIPPED"]
    print(label, "->", diagnostics)
