"""A-09: JSON import keeps rule ids; two sets with one id and different content fail.

Expect after the fix: prints "ok".
"""

import tempfile
from dataclasses import replace

import common  # noqa: F401
from rules.conflicts import validate_no_blocking_conflicts
from rules.exporters import export_rules
from rules.importers import import_rules, reassign_colliding_ids
from rules.models import Rule
from rules.store import RuleSet, RuleStore

store = RuleStore(tempfile.mkdtemp())
original = [Rule(id="r1", type="exact", direction="s2t", source="头发", target="頭髮")]
store.save(RuleSet("A", tuple(original)))
exported = export_rules(original, format="json")
store.save(RuleSet("A", (replace(original[0], enabled=False),)))
imported = import_rules(exported, format="json")
saved_rulesets, _errors = store.list()
existing_ids = {rule.id for ruleset in saved_rulesets for rule in ruleset.rules}
reassigned = reassign_colliding_ids(imported.rules, existing_ids)
print("imported ids:", [rule.id for rule in reassigned])
store.save(RuleSet("B", reassigned))
try:
    validate_no_blocking_conflicts(store.load_many(["A", "B"]))
    assert store.load("B").rules[0].id != original[0].id
    assert store.load("B").rules[0].source == original[0].source
    assert store.load("B").rules[0].target == original[0].target
    print("ok")
except Exception as error:  # noqa: BLE001 - repro prints whatever fails
    print("FAIL:", type(error).__name__, error)
