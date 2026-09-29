# ruff: noqa: E401, E402, E701, E702, E731, F401, F811, F841
"""FIX-02/FIX-03: rename desyncs run membership; delete + reuse id loses rules.

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
    it = iter(answers)
    return SimpleNamespace(getText=lambda *a, **k: (next(it), True))

def settings_with(root, sets, profile_ids):
    ProfileStore(root / "profiles").save(Profile(id="saved", name="Saved", ruleset_ids=profile_ids))
    store = RuleStore(root / "rules")
    for s in sets: store.save(s)
    st = RunSettings(Storage(root), SimpleNamespace(book_fingerprint=lambda: "BOOK"),
                     {"profile_id": "saved"}, language="en", session_id="s")
    st.bind_run(st.active, SimpleNamespace(available_configs=lambda: {"s2t"}))
    return st

modal_log = []
def yes(_qt, _p, _t, msg, _tr):
    modal_log.append(msg); return True
rw.ask_confirmation = yes
import app.settings as app_settings
app_settings.ask_confirmation = yes

print("=== A. rename a ruleset that is in the run ===")
w = RuleManagerDialog(make_with_table(), (), translator=Translator("en"), config="s2t",
    rulesets=(RuleSet("default"), RuleSet("A", (Rule(id="a1", source="软件", target="軟體", direction="s2t"),))),
    ruleset_id="A", run_ruleset_ids=("default", "A"))
print("before rename: use_in_run checked =", w.use_in_run_check.isChecked(),
      "| active filter count =", sum(w._rule_is_active(r) for r in w.rules))
w._qt.QInputDialog = names(["B"])
w._rename_ruleset()
print("after rename A->B: _run_ruleset_ids =", w._run_ruleset_ids,
      "| use_in_run checked =", w.use_in_run_check.isChecked(),
      "| rule a1 active =", w._rule_is_active(w.rules[0]),
      "| reason =", w._rule_activity_reason(w.rules[0]))
# user now wants to REMOVE it from this run: box is unchecked, so they tick then untick
w.use_in_run_check.setChecked(True); w.use_in_run_check.setChecked(False)
w._apply()
print("user ticked+unticked; result.run_ruleset_ids =", w.result.run_ruleset_ids, "renamed =", w.result.renamed)
with tempfile.TemporaryDirectory() as d:
    st = settings_with(Path(d), (RuleSet("A", w.result.rulesets[1].rules),), ("default", "A"))
    rw.show_rules_window = lambda *a, **k: w.result
    st.edit_rules("s2t", Translator("en"), make_with_table(), None)
    print("edit_rules -> active.ruleset_ids =", st.active.ruleset_ids, "(user expected B removed)")

print("\n=== A2. cross-ruleset conflict hidden after rename ===")
w = RuleManagerDialog(make_with_table(), (), translator=Translator("en"), config="s2t",
    rulesets=(RuleSet("A", (Rule(id="a1", source="软件", target="軟體", direction="s2t"),)),
              RuleSet("B", (Rule(id="b1", source="软件", target="軟件", direction="s2t"),))),
    ruleset_id="A", run_ruleset_ids=("A", "B"))
print("before: conflicts listed =", w.conflict_list.count(), "save enabled =", w.apply_button.isEnabled())
w.ruleset_combo.setCurrentIndex(w.ruleset_combo.findData("B"))
w._qt.QInputDialog = names(["B2"])
w._rename_ruleset()
w.ruleset_combo.setCurrentIndex(w.ruleset_combo.findData("A"))
print("after renaming B->B2: conflicts listed =", w.conflict_list.count(), "save enabled =", w.apply_button.isEnabled())
w._apply()
with tempfile.TemporaryDirectory() as d:
    st = settings_with(Path(d), (w.result.rulesets[0], RuleSet("B", w.result.rulesets[1].rules)), ("A", "B"))
    rw.show_rules_window = lambda *a, **k: w.result
    st.edit_rules("s2t", Translator("en"), make_with_table(), None)
    print("saved run ids =", st.active.ruleset_ids)
    try:
        st.freeze_rules(st.current_profile("s2t", {"ruleset_ids": list(st.active.ruleset_ids)}))
        print("freeze: OK")
    except Exception as e:
        print("freeze:", type(e).__name__, e)

print("\n=== B. delete X, then create a new X before Save ===")
with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    st = settings_with(root, (RuleSet("X", (Rule(id="old", source="旧", target="舊", direction="s2t"),)),), ("default", "X"))
    def window(rules, **kw):
        m = RuleManagerDialog(make_with_table(), rules, **kw)
        m.ruleset_combo.setCurrentIndex(m.ruleset_combo.findData("X"))
        m._delete_ruleset()
        m._qt.QInputDialog = names(["X"])
        m._new_ruleset()
        m.source_edit.setText("新"); m.target_edit.setText("新詞"); m._add()
        m.use_in_run_check.setChecked(True)
        m._apply()
        print("window result: sets =", [s.id for s in m.result.rulesets], "deleted =", m.result.deleted,
              "run =", m.result.run_ruleset_ids)
        return m.result
    rw.show_rules_window = window
    modal_log.clear()
    st.edit_rules("s2t", Translator("en"), make_with_table(), None)
    print("X.json exists after save:", (root / "rules" / "X.json").exists(),
          "| active.ruleset_ids =", st.active.ruleset_ids,
          "| saved profile =", ProfileStore(root / "profiles").load("saved").ruleset_ids)
    print("modals:", len(modal_log))

print("\n=== C. delete X, then rename Y -> X before Save ===")
with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    st = settings_with(root, (RuleSet("X"), RuleSet("Y", (Rule(id="y1", source="甲", target="乙", direction="s2t"),))), ("default", "Y"))
    def window(rules, **kw):
        m = RuleManagerDialog(make_with_table(), rules, **kw)
        m.ruleset_combo.setCurrentIndex(m.ruleset_combo.findData("X"))
        m._delete_ruleset()
        m.ruleset_combo.setCurrentIndex(m.ruleset_combo.findData("Y"))
        m._qt.QInputDialog = names(["X"])
        m._rename_ruleset()
        m._apply()
        print("window result: sets =", [s.id for s in m.result.rulesets], "renamed =", m.result.renamed,
              "deleted =", m.result.deleted, "run =", m.result.run_ruleset_ids)
        return m.result
    rw.show_rules_window = window
    st.edit_rules("s2t", Translator("en"), make_with_table(), None)
    print("files:", sorted(p.name for p in (root / "rules").glob("*.json")),
          "| active.ruleset_ids =", st.active.ruleset_ids,
          "| saved profile =", ProfileStore(root / "profiles").load("saved").ruleset_ids)
