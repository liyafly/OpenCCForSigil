# ruff: noqa: E401, E402, E701, E702, E731, F401, F811, F841
"""FIX-03/FIX-05: rename then new set with old id; confirming an addition persists a removal; modal count.

Run from the repository root. Read-only: uses temporary directories, never the user's data.
"""
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))
sys.path.insert(0, str(REPO))

import sys, tempfile
from pathlib import Path
from types import SimpleNamespace
from tests.support.fake_qt import make_with_table
import ui.rules_window as rw
import app.settings as app_settings
from ui.rules_window import RuleManagerDialog
from ui.i18n import Translator
from rules.models import Rule
from rules.store import RuleSet, RuleStore
from app.settings import RunSettings
from app.profiles import Profile, ProfileStore

class Storage:
    def __init__(self, root):
        self.paths = SimpleNamespace(root=root, profiles=root / "profiles", rules=root / "rules")
def names(answers):
    it = iter(answers); return SimpleNamespace(getText=lambda *a, **k: (next(it), True))
def settings_with(root, sets, profile_ids, others=()):
    ps = ProfileStore(root / "profiles")
    ps.save(Profile(id="saved", name="Saved", ruleset_ids=profile_ids))
    for p in others: ps.save(p)
    store = RuleStore(root / "rules")
    for s in sets: store.save(s)
    st = RunSettings(Storage(root), SimpleNamespace(book_fingerprint=lambda: "BOOK"),
                     {"profile_id": "saved"}, language="en", session_id="s")
    st.bind_run(st.active, SimpleNamespace(available_configs=lambda: {"s2t"}))
    return st, ps
log = []
def yes(_qt, _p, _t, msg, _tr): log.append(msg); return True
rw.ask_confirmation = yes; app_settings.ask_confirmation = yes

print("=== A3. rename A->B, then new A: new A's checkbox shows 'in run' but it is not ===")
with tempfile.TemporaryDirectory() as d:
    st, ps = settings_with(Path(d), (RuleSet("A", (Rule(id="a1", source="甲", target="乙", direction="s2t"),)),), ("default", "A"))
    def window(rules, **kw):
        m = RuleManagerDialog(make_with_table(), rules, **kw)
        m.ruleset_combo.setCurrentIndex(m.ruleset_combo.findData("A"))
        m._qt.QInputDialog = names(["B", "A"])
        m._rename_ruleset(); m._new_ruleset()
        print("new A: use_in_run checked =", m.use_in_run_check.isChecked())
        m.source_edit.setText("新"); m.target_edit.setText("新詞"); m._add()
        m._apply(); print("result.run_ruleset_ids =", m.result.run_ruleset_ids); return m.result
    rw.show_rules_window = window
    st.edit_rules("s2t", Translator("en"), make_with_table(), None)
    print("active.ruleset_ids =", st.active.ruleset_ids, "(new A with the visible tick is NOT in run)")

print("\n=== D. confirming an addition silently persists an unconfirmed removal ===")
with tempfile.TemporaryDirectory() as d:
    st, ps = settings_with(Path(d), (RuleSet("A"),), ("default", "A"))
    def window(rules, **kw):
        m = RuleManagerDialog(make_with_table(), rules, **kw)
        m.ruleset_combo.setCurrentIndex(m.ruleset_combo.findData("A"))
        m.use_in_run_check.setChecked(False)        # remove A from this run (session-only)
        m._qt.QInputDialog = names(["N"]); m._new_ruleset()
        m.use_in_run_check.setChecked(True)          # add N
        m._apply(); return m.result
    rw.show_rules_window = window
    log.clear()
    st.edit_rules("s2t", Translator("en"), make_with_table(), None)
    print("question asked:", log)
    print("saved profile now:", ps.load("saved").ruleset_ids, "(A removal was never asked about)")

print("\n=== E. modal count, one save with: disable shared set + delete referenced set + add new set ===")
with tempfile.TemporaryDirectory() as d:
    st, ps = settings_with(Path(d), (RuleSet("S"), RuleSet("X")), ("default", "S", "X"),
                           others=(Profile(id="o", name="Other", ruleset_ids=("S", "X")),))
    def window(rules, **kw):
        m = RuleManagerDialog(make_with_table(), rules, **kw)
        m.ruleset_combo.setCurrentIndex(m.ruleset_combo.findData("S"))
        m.ruleset_enabled_check.setChecked(False)
        n_disable = len(log)
        m.ruleset_combo.setCurrentIndex(m.ruleset_combo.findData("X")); m._delete_ruleset()
        n_delete = len(log) - n_disable
        m._qt.QInputDialog = names(["N"]); m._new_ruleset(); m.use_in_run_check.setChecked(True)
        m._apply(); window.counts = (n_disable, n_delete); return m.result
    rw.show_rules_window = window
    log.clear()
    st.edit_rules("s2t", Translator("en"), make_with_table(), None)
    print("in-window modals: disable=%d delete=%d | modals during Save (edit_rules)=%d" % (
        window.counts[0], window.counts[1], len(log) - sum(window.counts)))
    print("saved:", ps.load("saved").ruleset_ids, "other:", ps.load("o").ruleset_ids)
