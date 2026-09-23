"""Optional document/language controls, independent of the Sigil container."""

from core.transformation import FORCE_PIVOT_CHAINS
from opencc_backend.configs import base_config


_initial = {}
_metadata_available = True
_services = None


def configure_run_options(initial=None, *, metadata_available=True, services=None):
    """Temporary compatibility wrapper for callers not yet using constructor injection."""

    global _initial, _metadata_available, _services
    _initial = dict(initial) if isinstance(initial, dict) else {}
    _services = services
    _metadata_available = metadata_available


def option_enablement(config: str, values: dict) -> dict[str, bool]:
    """Return option-control availability for one direction and current values."""

    direction = base_config(config)
    compatible_chains = tuple(chain for chain in FORCE_PIVOT_CHAINS if chain[-1] == direction)
    language_mode = values.get("language_metadata", "keep")
    language_preset = values.get("language_preset", "legacy")
    return {
        "force_pivot": bool(compatible_chains),
        "pivot_chain": bool(compatible_chains and values.get("force_pivot", False)),
        "language_preset": language_mode != "keep",
        "language_region": (
            language_mode != "keep"
            and language_preset == "legacy"
            and direction in {"s2t", "tw2t", "hk2t"}
        ),
        "include_metadata": bool(values.get("metadata_available", True)),
    }


class RunOptionsPanel:
    def __init__(
        self, qt, translator, layout, *, initial=None, metadata_available=None, services=None
    ):
        self._qt = qt
        self._tr = translator
        self._initial = dict(_initial if initial is None else initial)
        self._metadata_available = (
            _metadata_available if metadata_available is None else bool(metadata_available)
        )
        self._services = _services if services is None else services
        self._preferred_pivot_chain = _pivot_chain_key(self._initial.get("pivot_chain", ()))
        self._enablement = {}
        self._updating = False
        self.checks = {}
        self.combos = {}
        self.profile_label = qt.QLabel()
        layout.addWidget(self.profile_label)
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
            control.setChecked(bool(self._initial.get(name, default)))
            if name == "include_metadata" and not self._metadata_available:
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
            index = combo.findData(self._initial.get(name, values[0]))
            combo.setCurrentIndex(max(0, index))
            self.combos[name] = combo
            form.addRow(translator.text("options." + name), combo)

        chain_combo = qt.QComboBox()
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
        self._connect_option_changes()

    def _connect_option_changes(self):
        for control in self.checks.values():
            control.stateChanged.connect(self._option_changed)
        for combo in self.combos.values():
            combo.currentIndexChanged.connect(self._option_changed)
        self.combos["pivot_chain"].currentIndexChanged.connect(self._pivot_chain_changed)

    def values(self):
        values = {
            **{name: control.isChecked() for name, control in self.checks.items()},
            **{name: combo.currentData() for name, combo in self.combos.items()
               if name != "pivot_chain"},
            "profile_id": self._services.active.id if self._services else self._initial.get("profile_id"),
            "ruleset_ids": list(self._services.active.ruleset_ids) if self._services
            else list(self._initial.get("ruleset_ids", ())),
        }
        chain = self.combos["pivot_chain"].currentData()
        values["pivot_chain"] = (
            _decode_pivot_chain(chain) if self._enablement.get("pivot_chain", False) else ()
        )
        if not self._metadata_available:
            values["include_metadata"] = False
        if not self._enablement.get("force_pivot", True):
            values["force_pivot"] = False
        return values

    def bind(self, config_getter, config_setter, parent):
        self._get_config, self._set_config, self._parent = config_getter, config_setter, parent
        self.update_enablement(config_getter())
        if self._services is None:
            return
        for name in ("profiles", "save_profile", "rules", "history", "self_test"):
            button = self._qt.QPushButton(self._tr.text("settings." + name))
            button.clicked.connect(lambda _checked=False, action=name: self._tool(action))
            self.tool_layout.addWidget(button)

    def update_enablement(self, config=None):
        if self._updating:
            return
        self._updating = True
        try:
            self._update_enablement(config)
        finally:
            self._updating = False

    def _update_enablement(self, config=None):
        if config is None:
            config = (self._get_config() if hasattr(self, "_get_config")
                      else self._initial.get("conversion", "s2t"))
        current_chain = self.combos["pivot_chain"].currentData()
        if current_chain:
            self._preferred_pivot_chain = _pivot_chain_key(current_chain)
        direction = base_config(str(config))
        compatible = tuple(sorted(chain for chain in FORCE_PIVOT_CHAINS if chain[-1] == direction))
        combo = self.combos["pivot_chain"]
        combo.clear()
        for chain in compatible:
            combo.addItem(" → ".join(chain), ">".join(chain))
        selected = combo.findData(self._preferred_pivot_chain)
        if selected < 0 and compatible:
            selected = 0
        if selected >= 0:
            combo.setCurrentIndex(selected)

        values = self.values()
        values["metadata_available"] = self._metadata_available
        self._enablement = option_enablement(str(config), values)
        if not self._enablement["force_pivot"]:
            self.checks["force_pivot"].setChecked(False)
        self.checks["force_pivot"].setEnabled(self._enablement["force_pivot"])
        combo.setEnabled(self._enablement["pivot_chain"])
        self.combos["language_preset"].setEnabled(self._enablement["language_preset"])
        self.combos["language_region"].setEnabled(self._enablement["language_region"])
        self.checks["include_metadata"].setEnabled(self._enablement["include_metadata"])
        if not self._enablement["include_metadata"]:
            self.checks["include_metadata"].setChecked(False)
        force_tip = (self._tr.text("options.force_pivot_unavailable", config=direction)
                     if not compatible else "")
        self.checks["force_pivot"].setToolTip(force_tip)
        if self._services is not None:
            self._update_profile_label(str(config))

    def validate(self, config):
        if self._services:
            profile = self._services.current_profile(config, self.values())
            self._services.freeze_rules(profile)
            missing = self._services.take_missing_rulesets_notice()
            if missing:
                self._qt.QMessageBox.information(
                    self._parent,
                    self._tr.text("options.title"),
                    self._tr.text("options.missing_rulesets", ids=", ".join(missing)),
                )

    def _option_changed(self, *_args):
        self.update_enablement()

    def _pivot_chain_changed(self, *_args):
        value = self.combos["pivot_chain"].currentData()
        if value:
            self._preferred_pivot_chain = _pivot_chain_key(value)
        self._option_changed()

    def _update_profile_label(self, config):
        from app.settings import settings_hash

        current = self._services.current_profile(config, self.values())
        active = self._services.active
        status = (self._tr.text("options.profile_modified")
                  if settings_hash(current) != settings_hash(active) else "")
        self.profile_label.setText(self._tr.text(
            "options.current_profile", name=active.name or active.id, status=status))

    def _tool(self, name):
        from app.settings import profile_options
        try:
            config = self._get_config()
            if name == "profiles":
                profile = self._services.pick_profile(config, self.values(), self._tr)
                if profile is not None:
                    values = profile_options(profile)
                    self._initial = values
                    for key, control in self.checks.items():
                        control.setChecked(bool(values.get(key, False)) if control.isEnabled() else False)
                    self._set_config(profile.conversion)
                    for key, combo in self.combos.items():
                        value = (_pivot_chain_key(values.get(key, ())) if key == "pivot_chain"
                                 else values.get(key, "keep"))
                        index = combo.findData(value)
                        if index >= 0:
                            combo.setCurrentIndex(index)
                    self.update_enablement(profile.conversion)
            elif name == "save_profile":
                self._services.save_profile(config, self.values(), self._tr, self._qt, self._parent)
                self.update_enablement(config)
            elif name == "rules":
                self._services.edit_rules(config, self._tr, self._qt, self._parent)
                self.update_enablement(config)
            else:
                self._services.open_tool(name, self._tr, self._qt, self._parent)
        except (ValueError, OSError) as exc:
            self._qt.QMessageBox.warning(self._parent, self._tr.text("options.title"), str(exc))


def _decode_pivot_chain(value):
    if isinstance(value, str):
        return tuple(part for part in value.split(">") if part)
    if isinstance(value, (tuple, list)):
        return tuple(str(part) for part in value)
    return ()


def _pivot_chain_key(value):
    return ">".join(_decode_pivot_chain(value))


def get_run_services():
    return _services


__all__ = ["ConfigurationChoice", "RunOptionsPanel", "configure_run_options",
           "get_run_services", "option_enablement"]


class ConfigurationChoice(str):
    """Keep the historical config string API while carrying frozen options."""

    def __new__(cls, config, options):
        from types import MappingProxyType

        instance = super().__new__(cls, config)
        instance.options = MappingProxyType(dict(options))
        return instance
