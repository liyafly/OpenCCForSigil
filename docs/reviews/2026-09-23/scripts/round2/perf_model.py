import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)
import time
from types import SimpleNamespace
from core.models import ConversionPlan, SourceSpan, TokenChange
from core.preview import PreviewSession
from ui.i18n import Translator
from ui.preview_window import _create_preview_table_model, _PreviewDialog

N = 50_000
FILES = 200
tr = Translator("zh-Hans")
changes_by_file = {}
for i in range(N):
    f = f"ch{i % FILES}"
    changes_by_file.setdefault(f, []).append(
        TokenChange(
            source="软件",
            target="軟體",
            span=SourceSpan(i, i + 2),
            rule_source="OpenCC:s2twp",
            change_id=f"c{i}",
            file_id=f,
            category="regional",
            risk="REVIEW",
            text_context_before="他使用这个",
            text_context_after="处理文件",
        )
    )
previews = tuple(
    PreviewSession(ConversionPlan(source_sha256="", file_id=f, changes=tuple(cs)))
    for f, cs in changes_by_file.items()
)
entries = tuple((p, c) for p in previews for c in p.changes)


class FakeIndex:
    def __init__(s, r, c):
        s._r, s._c = r, c

    def isValid(s):
        return s._r >= 0

    def row(s):
        return s._r

    def column(s):
        return s._c


class FakeModel:
    def __init__(s, parent=None):
        pass

    def beginResetModel(s):
        pass

    def endResetModel(s):
        pass

    def index(s, r, c):
        return FakeIndex(r, c)


Qt = SimpleNamespace(DisplayRole=0, ForegroundRole=9, FontRole=6, Horizontal=1)
qt = SimpleNamespace(
    QtCore=SimpleNamespace(QAbstractTableModel=FakeModel),
    Qt=Qt,
    QtGui=SimpleNamespace(
        QColor=lambda c: c, QFont=lambda: SimpleNamespace(setBold=lambda b: None)
    ),
)
Model = _create_preview_table_model(
    qt, entries, {f: f"Text/{f}.xhtml" for f in changes_by_file}, {}, tr
)
m = Model()
roles = [
    0,
    1,
    6,
    7,
    8,
    9,
    10,
    13,
]  # Display, Decoration, Font, TextAlignment, Background, Foreground, CheckState, SizeHint
t = time.perf_counter()
calls = 0
for r in range(1000):
    for col in (0, 1, 4, 5):
        idx = FakeIndex(r, col)
        for role in roles:
            m.data(idx, role)
            calls += 1
el = time.perf_counter() - t
print(
    f"data() calls: {calls}, total {el * 1000:.0f} ms, per call {el / calls * 1e6:.1f} us  (~one ResizeToContents pass over 4 cols x 1000 rows x 8 roles)"
)

# Python-side cost of one _refresh-equivalent pieces
d = object.__new__(_PreviewDialog)
d._translator = tr
d._previews = previews
d._entries = entries
d._planned = ()


class Combo:
    def __init__(s, v=None):
        s.v = v

    def currentData(s):
        return s.v


d.file_filter = Combo()
d.category_filter = Combo()
d.risk_filter = Combo()
t = time.perf_counter()
d._visible_entries()
print(f"_visible_entries (50k): {(time.perf_counter() - t) * 1000:.1f} ms")
t = time.perf_counter()
d._groups_for_file("ch1")
print(f"_groups_for_file per row change: {(time.perf_counter() - t) * 1000:.1f} ms")
