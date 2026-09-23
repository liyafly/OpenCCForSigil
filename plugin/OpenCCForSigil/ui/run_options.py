"""Optional document/language controls, independent of the Sigil container."""

from core.transformation import FORCE_PIVOT_CHAINS
from opencc_backend.configs import base_config
from ui.i18n import settings_error_message, show_error_details


def option_enablement(config: str, values: dict) -> dict[str, bool]:
    """Return option-control availability for one direction and current values."""

    direction = base_config(config)
    compatible_chains = tuple(chain for chain in FORCE_PIVOT_CHAINS if chain[-1] == direction)
    language_mode = values.get("language_metadata", "keep")
    language_preset = values.get("language_preset", "legacy")
    return {
        "include_nav": bool(values.get("nav_available", True)),
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
        self, qt, translator, layout, *, initial=None, metadata_available=None,
        nav_available=True, services=None, ui_preferences=None,
    ):
        self._qt = qt
        self._tr = translator
        self._initial = dict(initial) if isinstance(initial, dict) else {}
        self._metadata_available = True if metadata_available is None else bool(metadata_available)
        self._services = services
        self._nav_available = bool(nav_available)
        self._ui_preferences = dict(ui_preferences or {})
        self._advanced_expanded = bool(
            self._ui_preferences.get("run_options_advanced_expanded", False))
        self._preferred_pivot_chain = _pivot_chain_key(self._initial.get("pivot_chain", ()))
        self._enablement = {}
        self._updating = False
        self.checks = {}
        self.combos = {}
        self.profile_label = qt.QLabel()
        self.ruleset_label = qt.QLabel()
        body = qt.QWidget()
        body_layout = qt.QVBoxLayout(body)
        profile_row = qt.QHBoxLayout()
        profile_row.addWidget(self.profile_label, 1)
        self.profile_buttons_layout = qt.QHBoxLayout()
        profile_row.addLayout(self.profile_buttons_layout)
        body_layout.addLayout(profile_row)
        ruleset_row = qt.QHBoxLayout()
        ruleset_row.addWidget(self.ruleset_label, 1)
        self.rules_button_layout = qt.QHBoxLayout()
        ruleset_row.addLayout(self.rules_button_layout)
        body_layout.addLayout(ruleset_row)

        documents = qt.QGroupBox(translator.text("options.documents"))
        documents_layout = qt.QVBoxLayout(documents)
        for name, default in (("include_nav", True), ("include_ncx", False),
                              ("include_metadata", False)):
            self._add_check(documents_layout, name, default)
        body_layout.addWidget(documents)

        tool_button = qt.QToolButton()
        tool_button.setText(translator.text("settings.tools"))
        popup_mode = _enum_value(qt.QToolButton, "InstantPopup")
        if popup_mode is not None:
            tool_button.setPopupMode(popup_mode)
        self.tools_menu = qt.QMenu(tool_button)
        tool_button.setMenu(self.tools_menu)
        self._tool_actions = {}
        action_type = getattr(getattr(qt, "QtGui", None), "QAction", None)
        action_type = action_type or getattr(qt, "QAction", None)
        if action_type is not None:
            for name in ("history", "self_test"):
                action = action_type(translator.text("settings." + name), tool_button)
                action.triggered.connect(
                    lambda _checked=False, selected=name: self._tool(selected))
                self.tools_menu.addAction(action)
                self._tool_actions[name] = action
        self.advanced_button = qt.QToolButton()
        self.advanced_button.setText(translator.text("options.advanced"))
        self.advanced_button.setCheckable(True)
        self.advanced_button.setChecked(self._advanced_expanded)
        button_style = _enum_value(qt.Qt, "ToolButtonTextBesideIcon")
        if button_style is not None:
            self.advanced_button.setToolButtonStyle(button_style)
        self.advanced_content = qt.QWidget()
        advanced_layout = qt.QVBoxLayout(self.advanced_content)
        self._add_option_group(advanced_layout, "options.attributes", (
            ("convert_alt", True), ("convert_title", True),
            ("convert_aria_label", False)))
        self._add_option_group(advanced_layout, "options.content", (
            ("convert_ruby_rt", False), ("convert_code_pre", False),
            ("decode_numeric_cjk_refs", False)))
        punctuation_group = qt.QGroupBox(translator.text("options.punctuation"))
        punctuation_layout = qt.QFormLayout(punctuation_group)
        self._add_combo(punctuation_layout, "quotation_mode",
                        ("keep", "curly", "corner", "nested_corner"))
        self._add_combo(punctuation_layout, "punctuation_mode", ("keep", "horizontal"))
        advanced_layout.addWidget(punctuation_group)
        language_group = qt.QGroupBox(translator.text("options.language_tags"))
        language_form = qt.QFormLayout(language_group)
        self._add_combo(language_form, "language_metadata", ("keep", "suggest", "force"))
        self._add_combo(language_form, "language_preset", ("legacy", "bcp47"))
        self._add_combo(language_form, "language_region", ("", "zh-TW", "zh-HK"))
        language_note = qt.QLabel(translator.text("options.language_note"))
        language_note.setWordWrap(True)
        language_form.addRow(language_note)
        advanced_layout.addWidget(language_group)
        self._add_option_group(advanced_layout, "options.diagnostics", (
            ("diagnose_mixed", True), ("detailed_classification", True)))
        high_risk = qt.QGroupBox(translator.text("options.high_risk"))
        high_risk_layout = qt.QFormLayout(high_risk)
        self._add_check(high_risk_layout, "force_pivot", False)
        self._add_combo(high_risk_layout, "pivot_chain", ())
        advanced_layout.addWidget(high_risk)
        body_layout.addWidget(self.advanced_button)
        body_layout.addWidget(self.advanced_content)
        self.advanced_content.setVisible(self._advanced_expanded)
        self.advanced_button.toggled.connect(self._advanced_toggled)
        self._advanced_toggled(self._advanced_expanded)
        self.tool_layout = qt.QHBoxLayout()
        self.tool_layout.addWidget(tool_button)
        self.tool_layout.addStretch(1)
        layout.addLayout(self.tool_layout)
        scroll = qt.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        scroll.setMinimumHeight(280)
        layout.insertWidget(0, scroll)
        self._connect_option_changes()

    def _add_check(self, layout, name, default):
        control = self._qt.QCheckBox(self._tr.text("options." + name))
        control.setChecked(bool(self._initial.get(name, default)))
        self.checks[name] = control
        if name == "include_nav" and not self._nav_available:
            control.setChecked(False)
            control.setEnabled(False)
            control.setToolTip(self._tr.text("options.nav_unavailable"))
        if name == "include_metadata" and not self._metadata_available:
            control.setChecked(False)
            control.setEnabled(False)
        if hasattr(layout, "addRow"):
            layout.addRow(control)
        else:
            layout.addWidget(control)
        return control

    def _add_combo(self, layout, name, values):
        combo = self._qt.QComboBox()
        for value in values:
            combo.addItem(self._tr.text("options." + (value or "no_region")), value)
        if values:
            index = combo.findData(self._initial.get(name, values[0]))
            combo.setCurrentIndex(max(0, index))
        self.combos[name] = combo
        if hasattr(layout, "addRow"):
            layout.addRow(self._tr.text("options." + name), combo)
        else:
            layout.addWidget(combo)
        return combo

    def _add_option_group(self, parent_layout, title_key, fields):
        group = self._qt.QGroupBox(self._tr.text(title_key))
        group_layout = self._qt.QVBoxLayout(group)
        for name, default in fields:
            self._add_check(group_layout, name, default)
        parent_layout.addWidget(group)

    def _advanced_toggled(self, expanded):
        self._advanced_expanded = bool(expanded)
        self.advanced_content.setVisible(self._advanced_expanded)
        arrow_name = "DownArrow" if self._advanced_expanded else "RightArrow"
        arrow = _enum_value(self._qt.Qt, arrow_name)
        if arrow is not None:
            self.advanced_button.setArrowType(arrow)
        self._ui_preferences["run_options_advanced_expanded"] = self._advanced_expanded

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
        for name in ("profiles", "save_profile"):
            button = self._qt.QPushButton(self._tr.text("settings." + name))
            button.clicked.connect(lambda _checked=False, action=name: self._tool(action))
            self.profile_buttons_layout.addWidget(button)
        self.ruleset_button = self._qt.QPushButton(self._tr.text("settings.rules"))
        self.ruleset_button.clicked.connect(lambda _checked=False: self._tool("rules"))
        self.rules_button_layout.addWidget(self.ruleset_button)
        self._update_profile_label(str(config_getter()))

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
        values["nav_available"] = self._nav_available
        self._enablement = option_enablement(str(config), values)
        if not self._enablement["include_nav"]:
            self.checks["include_nav"].setChecked(False)
        self.checks["include_nav"].setEnabled(self._enablement["include_nav"])
        self.checks["include_nav"].setToolTip(
            "" if self._enablement["include_nav"]
            else self._tr.text("options.nav_unavailable"))
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
        self.ruleset_label.setText(self._tr.text(
            "options.active_rulesets", ids=", ".join(active.ruleset_ids) or "—"))

    def ui_state(self):
        return {"run_options_advanced_expanded": self._advanced_expanded}

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
            show_error_details(
                self._qt, self._parent, self._tr.text("options.title"),
                settings_error_message(self._tr, exc), str(exc),
            )


def _decode_pivot_chain(value):
    if isinstance(value, str):
        return tuple(part for part in value.split(">") if part)
    if isinstance(value, (tuple, list)):
        return tuple(str(part) for part in value)
    return ()


def _pivot_chain_key(value):
    return ">".join(_decode_pivot_chain(value))


def _enum_value(namespace, name):
    value = getattr(namespace, name, None)
    if value is not None:
        return value
    for enum_name in ("ToolButtonPopupMode", "ToolButtonStyle", "ArrowType"):
        value = getattr(getattr(namespace, enum_name, None), name, None)
        if value is not None:
            return value
    return None


__all__ = ["ConfigurationChoice", "RunOptionsPanel", "option_enablement"]


class ConfigurationChoice(str):
    """Keep the historical config string API while carrying frozen options."""

    def __new__(cls, config, options):
        from types import MappingProxyType

        instance = super().__new__(cls, config)
        instance.options = MappingProxyType(dict(options))
        return instance
