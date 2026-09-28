# ruff: noqa: E402,E702
"""RULE-14: foreign owners are labelled and can be rebound explicitly."""
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
                      run_options={"ruleset_ids": ("default",)},
                      run_ruleset_ids=("default",))
print("table scope column:", w.table.item(0, 4).text(), "| activity:", w._rule_activity_reason(old_book_rule))

# Editing a foreign rule does not silently change its owner. Rebinding is explicit.
w.table.selectRow(0); w._load_selected()
print("rebind button visible/enabled:", w.rebind_owner_button.isVisible(), w.rebind_owner_button.isEnabled())
print("before explicit rebind -> owner still old book:", w.rules[0].book_fingerprint == before)
w.rebind_owner_button.click()
print("after explicit rebind -> owner is current book:", w.rules[0].book_fingerprint == after)
