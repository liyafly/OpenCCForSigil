"""Optional document/language controls, independent of the Sigil container."""

from types import MappingProxyType


class ConfigurationChoice(str):
    """Keep the historical config string API while carrying frozen options."""

    def __new__(cls, config, options):
        instance = super().__new__(cls, config)
        instance.options = MappingProxyType(dict(options))
        return instance


_initial = {}
_metadata_available = True


def configure_run_options(initial=None, *, metadata_available=True):
    global _initial, _metadata_available
    _initial = dict(initial or {})
    _metadata_available = metadata_available


class RunOptionsPanel:
    def __init__(self, qt, translator, layout):
        self._qt = qt
        self._tr = translator
        self.checks = {}
        self.combos = {}
        box = qt.QGroupBox(translator.text("options.title"))
        form = qt.QFormLayout(box)
        for name, default in (("include_nav", True), ("include_ncx", False),
                              ("include_metadata", False)):
            control = qt.QCheckBox(translator.text("options." + name))
            control.setChecked(bool(_initial.get(name, default)))
            if name == "include_metadata" and not _metadata_available:
                control.setChecked(False)
                control.setEnabled(False)
            self.checks[name] = control
            form.addRow(control)
        for name, values in (
            ("language_metadata", ("keep", "suggest", "force")),
            ("language_preset", ("legacy", "bcp47")),
            ("language_region", ("", "zh-TW", "zh-HK")),
        ):
            combo = qt.QComboBox()
            for value in values:
                combo.addItem(translator.text("options." + (value or "no_region")), value)
            index = combo.findData(_initial.get(name, values[0]))
            combo.setCurrentIndex(max(0, index))
            if name == "language_metadata" and not _metadata_available:
                combo.setCurrentIndex(0)
                combo.setEnabled(False)
            self.combos[name] = combo
            form.addRow(translator.text("options." + name), combo)
        note = qt.QLabel(translator.text("options.language_note"))
        note.setWordWrap(True)
        form.addRow(note)
        layout.addWidget(box)

    def values(self):
        return {
            **{name: control.isChecked() for name, control in self.checks.items()},
            **{name: combo.currentData() for name, combo in self.combos.items()},
        }
