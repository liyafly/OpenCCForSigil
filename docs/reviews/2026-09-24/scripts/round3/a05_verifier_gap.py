"""A-05: the verifier accepts unplanned edits to protected attributes and blocks.

Expect after the fix: passed=False with UNPLANNED_CHANGE / PROTECTED_* codes.
"""

from dataclasses import replace

from common import backend, request
from core.models import SourceSpan, TokenChange
from core.planner import build_conversion_plan
from core.staging import StagingArea
from core.verifier import verify_staged_file
from document.tokenizer import tokenize_xhtml

source = ('<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
          '<body><p epub:type="footnote" role="doc-note">文</p><pre>汉字</pre><!--汉字-->'
          '<script>var a="汉字";</script></body></html>')
document = tokenize_xhtml(source)
plan = build_conversion_plan(file_id="a", source=source, document=document,
                             backend=backend("s2t"), request=request("s2t"))


def injected(text, new, nth=0):
    index = -1
    for _ in range(nth + 1):
        index = source.index(text, index + 1)
    return TokenChange(source=text, target=new, span=SourceSpan(index, index + len(text)),
                       rule_source="injected", change_id=f"x{index}")


bad = replace(plan, changes=(injected("footnote", "endnote"), injected("doc-note", "x"),
                             injected("汉字", "漢字", 0), injected("汉字", "漢字", 1),
                             injected("汉字", "漢字", 2)), allowed_spans=())
staged = StagingArea().stage("a", source, bad)
result = verify_staged_file(staged, original_document=document)
print("passed:", result.passed, [item.code for item in result.diagnostics])
