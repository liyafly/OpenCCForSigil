import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)
import fakeqt
from ui.preview_window import _ConversionConfigDialog
from ui.i18n import Translator
from opencc_backend.configs import V1_CONFIGS

qt = fakeqt.make()
qt.QDialogButtonBox = type("QDialogButtonBox", (fakeqt.Base,), {})


class BB(fakeqt.Base):
    StandardButton = type("SB", (), {"Cancel": 0x400000})
    ButtonRole = type("BR", (), {"ActionRole": 3, "AcceptRole": 0, "RejectRole": 1})

    def addButton(self, *a):
        b = qt.QPushButton(
            a[0] if isinstance(a[0], str) else f"<standard {a[0]:#x}: Qt-translated text>"
        )
        self.__dict__.setdefault("kids", []).append(b)
        return b


qt.QDialogButtonBox = BB
initial = {"force_pivot": True, "pivot_chain": ["s2tw", "t2s"], "conversion": "t2s"}
d = _ConversionConfigDialog(
    qt, tuple(V1_CONFIGS), "t2s", {}, translator=Translator("zh-Hans"), initial_options=initial
)
panel = d.options_panel
print("pivot combo items:", [it[1] for it in panel.combos["pivot_chain"].items])
print("initial preferred s2tw>t2s -> values()['pivot_chain'] =", panel.values()["pivot_chain"])
print("\nTop-level dialog layout order:")
for line in fakeqt.tree(d.dialog._layout):
    if not line.startswith("    "):
        print(line)
print("\ncancel button text:", d.cancel_button.text())
