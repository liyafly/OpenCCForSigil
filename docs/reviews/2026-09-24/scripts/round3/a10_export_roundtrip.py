"""A-10: TSV/CSV/TXT export loses enabled/type/priority (expect: warnings or lossless)."""

import common  # noqa: F401
from rules.exporters import export_rules
from rules.importers import import_rules
from rules.models import Rule

rules = [Rule(id="d", enabled=False, type="exact", direction="s2t", source="头发", target="頭發"),
         Rule(id="p", type="protect", direction="*", source="乾隆", priority=500),
         Rule(id="t", type="exact", direction="s2twp", source="苹果", target="Apple Inc")]
for fmt in ("tsv", "csv", "txt"):
    result = import_rules(export_rules(rules, format=fmt), format=fmt, direction="s2twp",
                          strict=False)
    print(fmt, [(r.enabled, r.type, r.source, r.target, r.priority) for r in result.rules],
          [d.message for d in result.diagnostics])
