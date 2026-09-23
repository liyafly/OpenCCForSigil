import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)
from common import plan
from rules.models import Rule

for src, rules in (
    ('<p>"他说<em>你好</em>"</p>', ()),
    ('<p>"软件"</p>', (Rule(id="p", type="protect", source="软件", direction="s2t"),)),
):
    book, wf, planned = plan(src, rules=rules, detailed=True, diag=True)
    for c in planned[0].plan.changes:
        print(repr(src), repr(c.source), "->", repr(c.target), c.category, c.rule_source, c.risk)
