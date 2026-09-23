import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)
import time
import fakeqt
from types import SimpleNamespace
from core.models import ConversionPlan, SourceSpan, TokenChange
from core.preview import PreviewSession
from ui.i18n import Translator
from ui.preview_window import _PreviewDialog

# Round 2 UI finding: _PreviewDialog.__init__ calls self._export_service(),
# which commit 1efe4e0 removed. Show the failure first, then patch it so the
# rest of this script can keep probing the dialog.
if not hasattr(_PreviewDialog, "_export_service"):
    print("BLOCKER: _PreviewDialog has no _export_service(); __init__ raises AttributeError")
    _PreviewDialog._export_service = lambda self: None


def build(n, files=2, lang_group=False):
    per = {}
    for i in range(n):
        f = f"f{i % files}"
        per.setdefault(f, []).append(
            TokenChange(
                source="后",
                target="後",
                span=SourceSpan(i, i + 1),
                rule_source="OpenCC:s2t",
                change_id=f"c{i}",
                file_id=f,
                category="character" if i % 3 else "phrase",
                risk="LOW",
                text_context_before="前",
                text_context_after="文",
            )
        )
    if lang_group:
        for f in list(per):
            per[f].append(
                TokenChange(
                    source="zh-CN",
                    target="zh-TW",
                    span=SourceSpan(10**6, 10**6 + 5),
                    rule_source="language_metadata",
                    change_id=f"lang-{f}",
                    file_id=f,
                    category="language_metadata",
                    risk="HIGH",
                    group_id="language_metadata",
                )
            )
    planned = tuple(
        SimpleNamespace(
            source=SimpleNamespace(file_id=f, href=f"Text/{f}.xhtml", document_kind="xhtml"),
            plan=ConversionPlan(source_sha256="", file_id=f, changes=tuple(cs)),
        )
        for f, cs in per.items()
    )
    previews = tuple(PreviewSession(p.plan) for p in planned)
    qt = fakeqt.make_with_table()
    d = _PreviewDialog(qt, planned, previews, Translator("en"), None)
    return d, qt


d, qt = build(6)


def cur():
    return d.table_view.currentIndex().row()


def ids():
    return [c.change_id for _, c in d._visible_entries_cache]


print("rows", ids(), "current", cur())
d._accept_this()
print("after accept row0 -> current", cur())
d._set_current_row(3)
d._accept_this()
print("after accept row3 -> current", cur())
# filter by category phrase; current is row 4 (c4, character). choose c3?
d._set_current_row(0)  # c0 phrase? c0 is phrase (i%3==0)
sel = d._selected_change_id()
d.category_filter.setCurrentIndex(d.category_filter.findData("phrase"))
print("after filter phrase: selected", sel, "->", d._selected_change_id(), ids())
print(
    "apply button:",
    d.apply_button.text(),
    d.apply_button.isEnabled(),
    "tooltip:",
    d.apply_button.toolTip(),
)
print("apply default:", d.apply_button.default, "autoDefault:", d.apply_button.auto_default)
others = [n for n in vars(d) if n.endswith("_button")]
print(
    "buttons with autoDefault(False):", [n for n in others if getattr(d, n).auto_default is False]
)
print("shortcuts:", [s.args[0] for s in d._shortcuts])
d._accept_all()
print("all accepted apply text:", d.apply_button.text(), d.apply_button.isEnabled())
d._reject_all()
print("all skipped apply text:", d.apply_button.text())
print("layout:")
print("\n".join(fakeqt.tree(d.dialog._layout)[:40]))

# group behaviour
d, qt = build(4, files=2, lang_group=True)
d._set_current_row(0)
print("group buttons visible:", d.accept_group_button.isVisible(), d.group_guidance.text())
d._accept_file()
print(
    "after accept file f0:",
    {
        c.change_id: (p.decision(c.change_id).value if p.decision(c.change_id) else None)
        for p, c in d._entries
    },
)
# perf 50k
for n in (10_000, 50_000):
    t = time.perf_counter()
    d, qt = build(n, files=100)
    t_build = time.perf_counter() - t
    d._set_current_row(0)
    t = time.perf_counter()
    d._accept_this()
    t1 = time.perf_counter() - t
    t = time.perf_counter()
    d._accept_file()
    t2 = time.perf_counter() - t
    t = time.perf_counter()
    d.category_filter.setCurrentIndex(1)
    t3 = time.perf_counter() - t
    t = time.perf_counter()
    d._accept_all()
    t4 = time.perf_counter() - t
    print(
        f"n={n}: build {t_build * 1000:.0f} ms, accept_this {t1 * 1000:.0f} ms, accept_file {t2 * 1000:.0f} ms, filter {t3 * 1000:.0f} ms, accept_all {t4 * 1000:.0f} ms (python only)"
    )
print("slot exceptions:", [e for e in fakeqt.LOG if isinstance(e, Exception)][:5])
d, qt = build(6)
d._accept_all()
print("file filter after accept all:", [it[0] for it in d.file_filter.items])
# group item single decision feedback persists?
d, qt = build(2, files=2, lang_group=True)
row = next(i for i, (_p, c) in enumerate(d._visible_entries_cache) if c.group_id)
d._set_current_row(row)
d._accept_this()
d._set_current_row(0)
d._reject_this()
print(
    "summary after later non-group action still shows group feedback:",
    "Decided together" in d.summary.text(),
)
