# ruff: noqa: E402,E702
"""RULE-14: rules owned by another book/profile are labelled '当前书'/'当前方案'; rebinding needs a detour."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace
REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))
sys.path.insert(0, str(REPO))

from rules.models import Rule
from sigil.adapter import SigilBookAdapter
from tests.support.fake_qt import make_with_table
from ui.i18n import Translator
from ui.rules_window import RuleManagerDialog

META = ('<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:identifier>urn:uuid:1111</dc:identifier>{extra}</metadata>')
def fp(extra=""):
    bk = SimpleNamespace(getmetadataxml=lambda: META.format(extra=extra), get_epub_filepath=lambda: "/b.epub")
    return SigilBookAdapter(bk).book_fingerprint()
before, after = fp(), fp("<dc:identifier>isbn:9787000000000</dc:identifier>")
print("fingerprint changes after adding an ISBN identifier:", before[:12], "->", after[:12])

old_book_rule = Rule(id="bk", direction="s2t", source="乾", target="幹", scope="book", book_fingerprint=before)
w = RuleManagerDialog(make_with_table(), (old_book_rule,), translator=Translator("zh-Hans"),
                      official_convert=lambda _c, v: v, config="s2t", book_fingerprint=after,
                      run_options={"ruleset_ids": ("default",)})
print("table scope column:", w.table.item(0, 4).text(), "| activity:", w._rule_activity_reason(old_book_rule))

# Try to re-bind it to the current book: select, keep scope '当前书', update.
w.table.selectRow(0); w._load_selected(); w.target_edit.setText("幹"); w._update_selected()
print("after update with scope unchanged -> owner still old book:", w.rules[0].book_fingerprint == before)
