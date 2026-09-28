# ruff: noqa: E402
"""RULE-11: '本次启用此规则集' is persisted in the ruleset file and disables it for every profile."""
import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))
sys.path.insert(0, str(REPO))

from app.profiles import Profile, ProfileStore
from app.settings import RunSettings
from rules.models import Rule
from rules.store import RuleSet, RuleStore
from tests.support.fake_qt import make_with_table
from ui import rules_window
from ui.i18n import Translator
from ui.rules_window import RuleWindowResult

root = Path(tempfile.mkdtemp())
storage = SimpleNamespace(paths=SimpleNamespace(root=root, profiles=root / "profiles", rules=root / "rules"))
RuleStore(root / "rules").save(RuleSet("shared", (Rule(id="r1", direction="s2t", source="软件", target="軟體"),)))
ProfileStore(root / "profiles").save(Profile(id="novel-a", name="A", conversion="s2t", ruleset_ids=("shared",)))
ProfileStore(root / "profiles").save(Profile(id="novel-b", name="B", conversion="s2t", ruleset_ids=("shared",)))

settings = RunSettings(storage, SimpleNamespace(book_fingerprint=lambda: "BOOK"),
                       {"profile_id": "novel-a"}, language="zh-Hans", session_id="s")
print("before: profile B freezes", [r.id for r in settings.freeze_rules(settings.profiles.load("novel-b")).rules])

# The user, working on profile A, unticks '本次启用此规则集' and presses '保存规则集'.
def fake_window(*_a, rulesets, ruleset_id, **_k):
    sets = tuple(replace(s, enabled=False) if s.id == "shared" else s for s in rulesets)
    return RuleWindowResult(ruleset_id, sets, ())
rules_window.show_rules_window = fake_window
settings.edit_rules("s2t", Translator("zh-Hans"), make_with_table(), None)

print("label shown to the user:", Translator("zh-Hans").text("rules.ruleset_enabled"))
print("after : shared.json enabled =", RuleStore(root / "rules").load("shared").enabled)
print("after : profile B (never touched) freezes", [r.id for r in settings.freeze_rules(settings.profiles.load("novel-b")).rules])

print("\n-- RULE-12: merely viewing another ruleset and saving adds it to this run --")
RuleStore(root / "rules").save(RuleSet("other", (Rule(id="o1", direction="s2t", source="内存", target="記憶體"),)))
fresh = RunSettings(storage, SimpleNamespace(book_fingerprint=lambda: "BOOK"), {},
                    language="zh-Hans", session_id="s2")
print("run ruleset_ids before:", fresh.active.ruleset_ids)
rules_window.show_rules_window = lambda *_a, rulesets, ruleset_id, **_k: RuleWindowResult(
    "other", tuple(rulesets), ())        # user only switched the combo to 'other', changed nothing
fresh.edit_rules("s2t", Translator("zh-Hans"), make_with_table(), None)
print("run ruleset_ids after :", fresh.active.ruleset_ids)
