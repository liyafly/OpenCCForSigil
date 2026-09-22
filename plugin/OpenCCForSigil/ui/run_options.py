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
_services = None


def configure_run_options(initial=None, *, metadata_available=True, services=None):
    global _initial, _metadata_available, _services
    _initial = dict(initial) if isinstance(initial, dict) else {}
    _services = services
    _metadata_available = metadata_available


class RunOptionsPanel:
    def __init__(self, qt, translator, layout):
        self._qt = qt
        self._tr = translator
        self._extra = dict(_initial)
        self._services = _services
        self.checks = {}
        self.combos = {}
        box = qt.QGroupBox(translator.text("options.title"))
        form = qt.QFormLayout(box)
        for name, default in (("include_nav", True), ("include_ncx", False),
                              ("include_metadata", False), ("convert_alt", True),
                              ("convert_title", True), ("convert_aria_label", False),
                              ("convert_ruby_rt", False), ("convert_code_pre", False),
                              ("decode_numeric_cjk_refs", False),
                              ("force_pivot", False), ("diagnose_mixed", True),
                              ("detailed_classification", True)):
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
            ("quotation_mode", ("keep", "curly", "corner", "nested_corner")),
            ("punctuation_mode", ("keep", "horizontal")),
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
        from core.transformation import FORCE_PIVOT_CHAINS
        chain_combo = qt.QComboBox()
        for chain in sorted(FORCE_PIVOT_CHAINS):
            chain_combo.addItem(" → ".join(chain), chain)
        chain_combo.setCurrentIndex(max(0, chain_combo.findData(tuple(_initial.get("pivot_chain", ())))))
        self.combos["pivot_chain"] = chain_combo
        form.addRow(translator.text("options.pivot_chain"), chain_combo)
        note = qt.QLabel(translator.text("options.language_note"))
        note.setWordWrap(True)
        form.addRow(note)
        scroll = qt.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(box)
        scroll.setMinimumHeight(280)
        scroll.setMaximumHeight(420)
        layout.addWidget(scroll)
        self.tool_layout = qt.QHBoxLayout()
        layout.addLayout(self.tool_layout)

    def values(self):
        return {
            **self._extra,
            **({"profile_id": self._services.active.id,
                "ruleset_ids": list(self._services.active.ruleset_ids)} if self._services else {}),
            **{name: control.isChecked() for name, control in self.checks.items()},
            **{name: combo.currentData() for name, combo in self.combos.items()},
        }

    def bind(self, config_getter, config_setter, parent):
        if self._services is None:
            return
        self._get_config, self._set_config, self._parent = config_getter, config_setter, parent
        for name in ("profiles", "save_profile", "rules", "history", "self_test"):
            button = self._qt.QPushButton(self._tr.text("settings." + name))
            button.clicked.connect(lambda _checked=False, action=name: self._tool(action))
            self.tool_layout.addWidget(button)

    def validate(self, config):
        if self._services:
            profile = self._services.current_profile(config, self.values())
            self._services.freeze_rules(profile)

    def _tool(self, name):
        from app.settings import profile_options
        try:
            config = self._get_config()
            if name == "profiles":
                profile = self._services.pick_profile(config, self.values(), self._tr)
                if profile is not None:
                    values = profile_options(profile)
                    self._extra = values
                    for key, control in self.checks.items():
                        control.setChecked(bool(values.get(key, False)) if control.isEnabled() else False)
                    for key, combo in self.combos.items():
                        combo.setCurrentIndex(max(0, combo.findData(values.get(key, "keep"))))
                    self._set_config(profile.conversion)
            elif name == "save_profile":
                self._services.save_profile(config, self.values(), self._tr, self._qt, self._parent)
            elif name == "rules":
                self._services.edit_rules(config, self._tr, self._qt, self._parent)
            else:
                self._services.open_tool(name, self._tr, self._qt, self._parent)
        except (ValueError, OSError) as exc:
            self._qt.QMessageBox.warning(self._parent, self._tr.text("options.title"), str(exc))


def get_run_services():
    return _services
