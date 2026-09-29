# ruff: noqa: E402,E702
import sys
import json
from pathlib import Path as _P; _ROOT = _P(__file__).resolve().parents[5]; sys.path.insert(0, str(_ROOT / "plugin/OpenCCForSigil"))
from PySide6.QtCore import QPoint
from ui.qt import load_qt, ensure_application
from ui.i18n import Translator
from ui.rules_window import RuleManagerDialog
from rules.models import Rule
qt = load_qt(); app = ensure_application(qt)
out = {}
for size in ((0, 0), (960, 640), (1280, 800)):
    tr = Translator("zh-Hans")
    rules = RuleManagerDialog(qt, tuple(Rule(id=f"r{i}", direction="s2t", source=f"软件{i}", target=f"軟體{i}") for i in range(30)), translator=tr)
    (rules.dialog.resize(*size) if size[0] else None); rules.dialog.show(); app.processEvents()
    vp = rules.editor_scroll.viewport()
    def inside(w):
        p = w.mapTo(vp, QPoint(0, 0))
        return vp.rect().contains(p) and vp.rect().contains(p + QPoint(w.width()-1, w.height()-1))
    tv = rules.table.viewport()
    rh = rules.table.verticalHeader().defaultSectionSize()
    out[str(size)] = {
        "actual": [rules.dialog.width(), rules.dialog.height()],
        "add_button_in_viewport": inside(rules.add_button),
        "source_edit_in_viewport": inside(rules.source_edit),
        "editor_scroll_max": rules.editor_scroll.verticalScrollBar().maximum(),
        "table_viewport_height": tv.height(), "table_rows_visible": tv.height() // max(rh, 1),
        "import_button_height": rules.ruleset_more_button.height(), "import_button_width": rules.ruleset_more_button.width(),
        "splitter_orientation": int(rules.editor_splitter.orientation().value),
    }
    rules.dialog.grab().save(f"/tmp/opencc-rules-viewport-{size[0]}.png")
    rules.dialog.done(0)
print(json.dumps(out, indent=1))
