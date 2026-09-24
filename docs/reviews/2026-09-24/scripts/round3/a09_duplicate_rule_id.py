"""A-09: JSON import keeps rule ids; two sets with one id and different content fail.

Expect after the fix: prints "ok".
"""

import tempfile
from dataclasses import replace

import common  # noqa: F401
from rules.conflicts import validate_no_blocking_conflicts
from rules.exporters import export_rules
from rules.importers import import_rules
from rules.models import Rule
from rules.store import RuleSet, RuleStore

store = RuleStore(tempfile.mkdtemp())
original = [Rule(id="r1", type="exact", direction="s2t", source="头发", target="頭髮")]
store.save(RuleSet("A", tuple(original)))
exported = export_rules(original, format="json")
store.save(RuleSet("A", (replace(original[0], target="頭发"),)))
imported = import_rules(exported, format="json")
print("imported ids:", [rule.id for rule in imported.rules])
store.save(RuleSet("B", imported.rules))
try:
    validate_no_blocking_conflicts(store.load_many(["A", "B"]))
    print("ok")
except Exception as error:  # noqa: BLE001 - repro prints whatever fails
    print("FAIL:", type(error).__name__, error)
