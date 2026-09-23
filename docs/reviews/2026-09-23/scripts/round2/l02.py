import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)
from common import plan, stage_all
from rules.models import Rule


def run(src, rules, **kw):
    book, wf, planned = plan(src, rules=rules, quotation_mode=kw.pop("q", "keep"), **kw)
    p = planned[0].plan
    try:
        staged, ver = stage_all(wf, planned)
        print(
            repr(src),
            "->",
            repr(staged[0].converted) if staged else None,
            [(v.passed, [d.code for d in v.diagnostics]) for v in ver],
        )
    except Exception as e:
        print(repr(src), "EXC", type(e).__name__, e)
    for c in p.changes:
        print("   ", repr(c.source), "->", repr(c.target), c.category)


run('<p title="称呼">称呼</p>', (Rule(id="r", source="称呼", target="a>b", direction="s2t"),))
run("<p>称呼&gt;x</p>", (Rule(id="r", source="称呼", target="x]]", direction="s2t"),))
run("<p>]]称呼</p>", (Rule(id="r", source="称呼", target=">", direction="s2t"),))
run("<p>a]]称呼</p>", (Rule(id="r", source="称呼", target="&gt;", direction="s2t"),))
# CDATA in xhtml
run("<p><![CDATA[汉字]]></p>", ())
run('<script>//<![CDATA[\n"汉"\n//]]></script><p>"汉"</p>', (), q="corner")
