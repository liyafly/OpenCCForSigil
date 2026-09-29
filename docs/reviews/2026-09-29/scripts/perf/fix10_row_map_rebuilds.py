# ruff: noqa: E401, E402, E701, E702, E731, F401, F811, F841
"""FIX-10: grouped decisions under the undecided filter rebuild the O(N) row map every click.

Run from the repository root. Read-only: uses temporary directories, never the user's data.
"""
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))
sys.path.insert(0, str(REPO))

import sys
from types import SimpleNamespace
from core.models import ConversionPlan, SourceSpan, TokenChange
from core.preview import PreviewSession
from tests.support.fake_qt import make_with_table
from ui.i18n import Translator
from ui.preview_window import _PreviewDialog
changes = tuple(TokenChange(source="旧", target="新", span=SourceSpan(i * 2, i * 2 + 1),
    rule_source="UserRule:a", change_id=f"c{i}", file_id="f.xhtml", category="user_rule",
    risk="HIGH", group_id=f"rules:g{i // 2}") for i in range(20_000))
p = PreviewSession(ConversionPlan(source_sha256="", file_id="f.xhtml", changes=changes))
d = _PreviewDialog(make_with_table(), (SimpleNamespace(source=SimpleNamespace(file_id="f.xhtml", href="Text/f.xhtml", document_kind="xhtml"), plan=p.plan),), (p,), Translator("en"))
d.status_filter.setCurrentIndex(d.status_filter.findData("undecided"))
built = []
orig = _PreviewDialog._visible_row_map
def wrap(self, entries):
    if not (self._visible_identity_to_row is not None and self._visible_identity_to_row_entries is entries):
        built.append(len(entries))
    return orig(self, entries)
_PreviewDialog._visible_row_map = wrap
for k in range(5):
    d._set_current_row(100)
    d._accept_this()
print("grouped accept x5 under undecided filter: row-map rebuilds =", len(built), "entries iterated =", sum(built))
