import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)
import fakeqt
from ui.preview_window import _ScopeDialog
from ui.i18n import Translator
from sigil.scope import TextFile

inv = (TextFile("a", "Text/a.xhtml"), TextFile("b", "Text/b.xhtml"), TextFile("nav", "nav.xhtml"))
for initial in (("a",), ("a", "b"), ()):
    qt = fakeqt.make()
    d = _ScopeDialog(qt, inv, initial, "en", Translator("en"), spine_ids=("a", "b"), nav_id="nav")
    mode = [
        r
        for r in ("single_radio", "selected_radio", "spine_radio", "all_radio")
        if getattr(d, r).isChecked()
    ]
    print(
        "initial",
        initial,
        "mode",
        mode,
        "analyze enabled:",
        d.analyze_button.isEnabled(),
        "selected_ids:",
        d.selected_ids(),
        "count:",
        d.count_label.text(),
    )
    if initial == ("a",):
        # user clicks row 2 in single mode
        d.list_widget.setCurrentRow(1)
        print("  after clicking row b: enabled", d.analyze_button.isEnabled(), d.selected_ids())
        print(
            "  check indicator data still present on items (shown by delegate):",
            [d.list_widget.item(i).data(qt.Qt.CheckStateRole) for i in range(3)],
        )
        print("  labels:", [d.list_widget.item(i).text() for i in range(3)])
        d.all_radio.setChecked(True)
        print(
            "  all mode: enabled",
            d.analyze_button.isEnabled(),
            "checks",
            [d.list_widget.item(i).checkState() for i in range(3)],
        )
        d.single_radio.setChecked(True)
        print(
            "  back to single: enabled",
            d.analyze_button.isEnabled(),
            "current row",
            d.list_widget.currentRow(),
            d.selected_ids(),
        )
print("slot exceptions:", [e for e in fakeqt.LOG if isinstance(e, Exception)])
