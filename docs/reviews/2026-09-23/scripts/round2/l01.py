import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)
from common import plan, stage_all

cases = [
    '<p>"他说<em>你好</em>"</p>',
    '<p>"甲"乙"</p>',
    '<p>"软件"</p>',
    '<p>"他说&amp;"</p>',
    '<p>"甲<br/>乙"</p>',
    '<pre>"甲</pre><pre>乙"</pre>',
    '<table><tr><td>"甲</td></tr></table><ul><li>乙"</li></ul>',
    '<p>"甲<span lang="en">"x"</span>乙"</p>',
    '<p>&#34;甲"</p>',
    '<p>"甲&#x5B57;"</p>',
]
for src in cases:
    book, wf, planned = plan(src)
    p = planned[0].plan
    staged, ver = stage_all(wf, planned)
    print(repr(src))
    print("  ->", staged[0].converted if staged else None, "verify", [v.passed for v in ver])
    for c in p.changes:
        print("   ", repr(c.source), "->", repr(c.target), c.category, c.rule_source, c.risk)
    print("   diags", [d.code for d in p.diagnostics])
