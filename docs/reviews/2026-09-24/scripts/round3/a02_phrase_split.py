"""A-02: one OpenCC phrase mapping is split into separately decidable changes.

Expect after the fix: every "only accept change i" result is either the source
or the full OpenCC output for that phrase, never a mix such as 印机 or 打印表機.
"""

from common import XHTML, PreviewSession, run
from core.staging import apply_changes

for text in ("打印机", "激光打印机坏了", "鼠标和内存"):
    source = XHTML.format(f"<p>{text}</p>")
    _book, _wf, planned, _staged = run(source, config="s2twp", commit=False,
                                       detailed=True, diag=True)
    plan = planned[0].plan
    print(text, [(c.source, c.target, c.category, c.group_id) for c in plan.changes])
    for index, change in enumerate(plan.changes):
        preview = PreviewSession(plan)
        preview.accept_this(change.change_id)
        preview.reject_all()
        body = apply_changes(source, preview.finalize().changes)
        print(f"  only #{index} ->", body[body.index("<p>"):body.index("</p>") + 4])
