# ruff: noqa: E402
"""RULE-05: conflicts between two rulesets of the same run are invisible in the manager."""
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))
sys.path.insert(0, str(REPO))

from app.profiles import Profile
from app.settings import RunSettings
from rules.conflicts import find_conflicts
from rules.models import Rule
from rules.store import RuleSet
from tests.support.fake_qt import make_with_table
from ui.i18n import Translator
from ui.rules_window import RuleManagerDialog

a = Rule(id="a1", type="exact", direction="s2t", source="软件", target="軟體")      # ruleset "taiwan-terms"
b = Rule(id="b1", type="exact", direction="s2t", source="软件", target="軟件")      # ruleset "default"
rulesets = (
    RuleSet("taiwan-terms", (a,), name="Taiwan terms"),
    RuleSet("default", (b,), name="Default"),
)
for identifier in ("taiwan-terms", "default"):
    current = next(item for item in rulesets if item.id == identifier)
    manager = RuleManagerDialog(
        make_with_table(), current.rules, translator=Translator("en"), config="s2t",
        run_options={"ruleset_ids": ["taiwan-terms", "default"]},
        rulesets=rulesets, ruleset_id=identifier,
    )
    shown = [manager.conflict_list.item(i).text()
             for i in range(manager.conflict_list.count())]
    print(f"conflicts shown while editing set {identifier}:", shown)
    print(f"save enabled for set {identifier}:", manager.apply_button.isEnabled())

with TemporaryDirectory() as directory:
    root = Path(directory)
    storage = SimpleNamespace(paths=SimpleNamespace(
        root=root, profiles=root / "profiles", rules=root / "rules"))
    settings = RunSettings(
        storage, SimpleNamespace(), {}, language="en", session_id="rule05-probe")
    for ruleset in rulesets:
        settings.rules.save(ruleset)
    try:
        settings.freeze_rules(Profile(
            id="profile", conversion="s2t",
            ruleset_ids=("taiwan-terms", "default"), builtin_rules_enabled=False))
        print("analysis preflight: OK")
    except Exception as exc:
        print("analysis preflight:", type(exc).__name__, "->", exc)

print("\n-- Spec §83 example: global vs profile rule for the same source (shadowing) --")
g = Rule(id="g", type="exact", direction="s2twp", source="服务器", target="伺服器", scope="global",
         semantic_version=2, action="override", stage="source")
p = Rule(id="p", type="exact", direction="s2twp", source="服务器", target="服務器", scope="profile",
         profile_id="P", priority=200, semantic_version=2, action="override", stage="source")
print("find_conflicts -> ", find_conflicts([g, p]), "(spec §83 wants the pair listed with 'Winner: profile rule')")
protect = Rule(id="keep", type="protect", direction="s2twp", source="服务器")
print("protect + exact with identical source -> ", find_conflicts([protect, g]),
      "(the exact rule can never apply; nothing tells the user)")
