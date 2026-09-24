"""N-02 (R-16 leftover): opening the settings dialog replaces a saved t2s pivot chain.

Expect after the fix: values == prefs == the chain passed in, for every row.
"""

import common  # noqa: F401
from opencc_backend.configs import V1_CONFIGS
from tests.support import fake_qt
from ui.i18n import Translator
from ui.preview_window import _ConversionConfigDialog

for direction, chain in (("t2s", ["s2tw", "t2s"]), ("t2s", ["s2twp", "t2s"]),
                         ("s2tw", ["t2s", "s2tw"]), ("s2t", ["t2s", "s2t"])):
    dialog = _ConversionConfigDialog(
        fake_qt.make(), tuple(V1_CONFIGS), direction, {}, translator=Translator("en"),
        initial_options={"force_pivot": True, "pivot_chain": chain})
    panel = dialog.options_panel
    print(direction, chain, "-> values", panel.values()["pivot_chain"],
          "prefs", panel.preference_values()["pivot_chain"])
