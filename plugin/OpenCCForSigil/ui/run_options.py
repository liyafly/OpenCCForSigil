"""Optional document/language controls, independent of the Sigil container."""

from dataclasses import replace

from core.transformation import FORCE_PIVOT_CHAINS
from opencc_backend.configs import base_config
from ui.i18n import (
    plugin_window_title,
    profile_display_name,
    settings_error_message,
    show_error_details,
)
from ui.qt import enum_value, exec_dialog
from transforms.language_tags import normalize_language_mode

_ADVANCED_FIELDS = frozenset({
    "convert_alt", "convert_title", "convert_aria_label", "convert_svg_text",
    "convert_ruby_rt", "convert_code_pre", "decode_numeric_cjk_refs",
    "quotation_mode", "punctuation_mode", "language_metadata", "language_preset",
    "language_region", "force_pivot", "pivot_chain", "mathml", "regex_rules",
    "tofu_policy", "numeric_cjk_char_refs",
})
_HIGH_RISK_FIELDS = ("force_pivot", "convert_metadata", "regex_rules")


def option_enablement(config: str, values: dict) -> dict[str, bool]:
    """Return option-control availability for one direction and current values."""

    direction = base_config(config)
    compatible_chains = tuple(chain for chain in FORCE_PIVOT_CHAINS if chain[-1] == config)
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
        self, qt, translator, layout, *, initial=None, metadata_available=None,
        services=None, ui_preferences=None,
    ):
        self._qt = qt
        self._tr = translator
        self._initial = dict(initial) if isinstance(initial, dict) else {}
        if "language_metadata" in self._initial:
            self._initial["language_metadata"] = normalize_language_mode(
                self._initial["language_metadata"])
        self._metadata_available = True if metadata_available is None else bool(metadata_available)
        self._services = services
        self._ui_preferences = dict(ui_preferences or {})
        self._advanced_expanded = bool(
            self._ui_preferences.get("run_options_advanced_expanded", False))
        self._preferred_pivot_chain = _pivot_chain_key(self._initial.get("pivot_chain", ()))
        self._enablement = {}
        self._updating = False
        self.checks = {}
        self.combos = {}
        self.combo_labels = {}
        self._combo_values = {}
        self._option_groups = []
        self._summary_changed_callback = None
        self._named_groups = []
        self._profile_buttons = []
        self._profile_changes = ()
        self._profile_baseline_label = ""
        self.profile_label = qt.QLabel()
        self.ruleset_label = qt.QLabel()
        size_policy = getattr(qt.QSizePolicy, "Policy", qt.QSizePolicy)
        preferred = getattr(size_policy, "Preferred", None)
        maximum = getattr(size_policy, "Maximum", None)
        if preferred is not None and maximum is not None:
            self.profile_label.setSizePolicy(preferred, maximum)
            self.ruleset_label.setSizePolicy(preferred, maximum)
        body = qt.QWidget()
        body_layout = qt.QVBoxLayout(body)
        profile_row = qt.QHBoxLayout()
        profile_row.addWidget(self.profile_label, 1)
        self.view_changes_button = qt.QPushButton(translator.text("options.view_changes"))
        self.view_changes_button.setVisible(False)
        self.view_changes_button.clicked.connect(self._show_profile_changes)
        profile_row.addWidget(self.view_changes_button)
        self.profile_buttons_layout = qt.QHBoxLayout()
        profile_row.addLayout(self.profile_buttons_layout)
        body_layout.addLayout(profile_row)
        ruleset_row = qt.QHBoxLayout()
        ruleset_row.addWidget(self.ruleset_label, 1)
        self.rules_button_layout = qt.QHBoxLayout()
        ruleset_row.addLayout(self.rules_button_layout)
        body_layout.addLayout(ruleset_row)
        builtin_rules_check = qt.QCheckBox(translator.text("options.builtin_rules_enabled"))
        builtin_rules_check.setChecked(bool(self._initial.get("builtin_rules_enabled", True)))
        self.checks["builtin_rules_enabled"] = builtin_rules_check
        body_layout.addWidget(builtin_rules_check)

        self.documents_group = qt.QGroupBox(translator.text("options.documents"))
        documents_layout = qt.QVBoxLayout(self.documents_group)
        for name, default in (("include_ncx", False), ("include_metadata", False)):
            self._add_check(documents_layout, name, default)
        body_layout.addWidget(self.documents_group)

        self.tool_button = qt.QToolButton()
        self.tool_button.setText(translator.text("settings.tools"))
        popup_mode = enum_value(qt.QToolButton, "InstantPopup")
        if popup_mode is not None:
            self.tool_button.setPopupMode(popup_mode)
        self.tools_menu = qt.QMenu(self.tool_button)
        self.tool_button.setMenu(self.tools_menu)
        self._tool_actions = {}
        action_type = getattr(getattr(qt, "QtGui", None), "QAction", None)
        action_type = action_type or getattr(qt, "QAction", None)
        if action_type is not None:
            for name in ("history", "self_test"):
                action = action_type(translator.text("settings." + name), self.tool_button)
                action.triggered.connect(
                    lambda _checked=False, selected=name: self._tool(selected))
                self.tools_menu.addAction(action)
                self._tool_actions[name] = action
        self.advanced_button = qt.QToolButton()
        self.advanced_button.setText(translator.text("options.advanced"))
        self.advanced_button.setCheckable(True)
        self.advanced_button.setChecked(self._advanced_expanded)
        button_style = enum_value(qt.Qt, "ToolButtonTextBesideIcon")
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
        self._named_groups.append((punctuation_group, "options.punctuation"))
        punctuation_layout = qt.QFormLayout(punctuation_group)
        self._add_combo(punctuation_layout, "quotation_mode",
                        ("keep", "curly", "corner", "nested_corner"))
        self._add_combo(punctuation_layout, "punctuation_mode", ("keep", "horizontal"))
        advanced_layout.addWidget(punctuation_group)
        language_group = qt.QGroupBox(translator.text("options.language_tags"))
        self._named_groups.append((language_group, "options.language_tags"))
        language_form = qt.QFormLayout(language_group)
        self._add_combo(language_form, "language_metadata", ("keep", "force"))
        self._add_combo(language_form, "language_preset", ("legacy", "bcp47"))
        self._add_combo(language_form, "language_region", ("", "zh-TW", "zh-HK"))
        self.language_note = qt.QLabel(translator.text("options.language_note"))
        self.language_note.setWordWrap(True)
        language_form.addRow(self.language_note)
        advanced_layout.addWidget(language_group)
        high_risk = qt.QGroupBox(translator.text("options.high_risk"))
        self._named_groups.append((high_risk, "options.high_risk"))
        high_risk_layout = qt.QFormLayout(high_risk)
        self._add_check(high_risk_layout, "force_pivot", False)
        self._add_combo(high_risk_layout, "pivot_chain", ())
        advanced_layout.addWidget(high_risk)
        body_layout.addWidget(self.advanced_button)
        body_layout.addWidget(self.advanced_content)
        body_layout.addStretch(1)
        self.advanced_content.setVisible(self._advanced_expanded)
        self.advanced_button.toggled.connect(self._advanced_toggled)
        self._advanced_toggled(self._advanced_expanded)
        self.tool_layout = qt.QHBoxLayout()
        self.tool_layout.addWidget(self.tool_button)
        self.tool_layout.addStretch(1)
        scroll = qt.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        scroll.setMinimumHeight(280)
        layout.addWidget(scroll)
        layout.addLayout(self.tool_layout)
        self._connect_option_changes()

    def _add_check(self, layout, name, default):
        control = self._qt.QCheckBox(self._tr.text("options." + name))
        control.setChecked(bool(self._initial.get(name, default)))
        self.checks[name] = control
        if name == "include_metadata" and not self._metadata_available:
            control.setEnabled(False)
        if hasattr(layout, "addRow"):
            layout.addRow(control)
        else:
            layout.addWidget(control)
        return control

    def _add_combo(self, layout, name, values):
        combo = self._qt.QComboBox()
        values = tuple(values)
        self._combo_values[name] = values
        for value in values:
            combo.addItem(self._tr.text("options." + (value or "no_region")), value)
        if values:
            index = combo.findData(self._initial.get(name, values[0]))
            combo.setCurrentIndex(max(0, index))
        self.combos[name] = combo
        if hasattr(layout, "addRow"):
            label = self._qt.QLabel(self._tr.text("options." + name))
            label.setBuddy(combo)
            self.combo_labels[name] = label
            layout.addRow(label, combo)
        else:
            layout.addWidget(combo)
        return combo

    def _add_option_group(self, parent_layout, title_key, fields):
        group = self._qt.QGroupBox(self._tr.text(title_key))
        self._option_groups.append((group, title_key))
        group_layout = self._qt.QVBoxLayout(group)
        for name, default in fields:
            self._add_check(group_layout, name, default)
        parent_layout.addWidget(group)

    def _advanced_toggled(self, expanded):
        self._advanced_expanded = bool(expanded)
        self.advanced_content.setVisible(self._advanced_expanded)
        arrow_name = "DownArrow" if self._advanced_expanded else "RightArrow"
        arrow = enum_value(self._qt.Qt, arrow_name)
        if arrow is not None:
            self.advanced_button.setArrowType(arrow)
        self._ui_preferences["run_options_advanced_expanded"] = self._advanced_expanded

    def _connect_option_changes(self):
        for control in self.checks.values():
            control.stateChanged.connect(self._option_changed)
        for name, combo in self.combos.items():
            if name != "pivot_chain":
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

    def preference_values(self):
        """Return the user's selections, including temporarily disabled options."""
        values = self.values()
        checks = getattr(self, "checks", {})
        for name in ("include_metadata", "force_pivot"):
            control = checks.get(name)
            if control is not None:
                values[name] = control.isChecked()
        preferred_chain = getattr(self, "_preferred_pivot_chain", "")
        if preferred_chain:
            values["pivot_chain"] = _decode_pivot_chain(preferred_chain)
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
            self._profile_buttons.append((button, name))
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
        compatible = tuple(sorted(chain for chain in FORCE_PIVOT_CHAINS if chain[-1] == str(config)))
        combo = self.combos["pivot_chain"]
        previously_blocked = combo.blockSignals(True)
        try:
            combo.clear()
            for chain in compatible:
                combo.addItem(" → ".join(chain), ">".join(chain))
        finally:
            combo.blockSignals(previously_blocked)
        selected = combo.findData(self._preferred_pivot_chain)
        if selected < 0 and compatible:
            selected = 0
        if selected >= 0:
            combo.setCurrentIndex(selected)

        values = self.values()
        values["metadata_available"] = self._metadata_available
        self._enablement = option_enablement(str(config), values)
        self.checks["force_pivot"].setEnabled(self._enablement["force_pivot"])
        combo.setEnabled(self._enablement["pivot_chain"])
        self.combos["language_preset"].setEnabled(self._enablement["language_preset"])
        self.combos["language_region"].setEnabled(self._enablement["language_region"])
        self.checks["include_metadata"].setEnabled(self._enablement["include_metadata"])
        if not compatible and str(config).endswith("_jieba"):
            force_tip = self._tr.text("options.force_pivot_jieba_unavailable")
        else:
            force_tip = (self._tr.text("options.force_pivot_unavailable", config=str(config))
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
                    plugin_window_title(self._tr, self._tr.text("options.title")),
                    self._tr.text("options.missing_rulesets", ids=", ".join(missing)),
                )

    def _option_changed(self, *_args):
        self.update_enablement()
        callback = self._summary_changed_callback
        if callable(callback):
            callback()

    def _pivot_chain_changed(self, *_args):
        value = self.combos["pivot_chain"].currentData()
        if value:
            self._preferred_pivot_chain = _pivot_chain_key(value)
        self._option_changed()

    def _update_profile_label(self, config):
        from app.settings import profile_options
        from ui.profile_window import _profile_signature
        from ui.profile_compare import compare_profile_settings

        preferred_values = (self.preference_values() if hasattr(self, "preference_values")
                            else self.values())
        current = self._profile_for_values(config, preferred_values, preserve_disabled=True)
        active = self._services.active
        normalized_active = self._services.current_profile(
            active.conversion, profile_options(active))
        status = (self._tr.text("options.profile_modified")
                  if _profile_signature(current) != _profile_signature(normalized_active) else "")
        self.profile_label.setText(self._tr.text(
            "options.current_profile", name=profile_display_name(active, self._tr), status=status))
        self.ruleset_label.setText(self._tr.text(
            "options.active_rulesets",
            ids=", ".join(current.ruleset_ids) or "—",
            builtin=(self._tr.text("options.builtin_on")
                     if current.builtin_rules_enabled
                     else self._tr.text("options.builtin_off")),
        ))
        self._profile_changes = compare_profile_settings(active, current)
        baseline_key = ("options.saved_profile"
                        if getattr(self._services, "active_profile_is_saved", False)
                        else "options.initial_settings")
        try:
            self._profile_baseline_label = self._tr.text(baseline_key)
        except KeyError:
            self._profile_baseline_label = baseline_key
        view_changes_button = getattr(self, "view_changes_button", None)
        if view_changes_button is not None:
            view_changes_button.setVisible(True)
        self._refresh_advanced_label()

    def _refresh_advanced_label(self):
        if not hasattr(self, "advanced_button"):
            return
        advanced_count = sum(name in _ADVANCED_FIELDS
                             for name, _old, _new in getattr(self, "_profile_changes", ()))
        risks = self._current_risks()
        self.advanced_button.setText(self._tr.text(
            "options.advanced_summary", count=advanced_count,
            risks=(self._tr.text("options.advanced_risks", items=" · ".join(risks))
                   if risks else "")))

    def _current_risks(self):
        if not hasattr(self, "_get_config") or self._services is None:
            return ()
        from app.settings import profile_options

        values = self.preference_values() if hasattr(self, "preference_values") else self.values()
        current = self._profile_for_values(self._get_config(), values, preserve_disabled=True)
        values = profile_options(current)
        return tuple(self._effective_display(
            key, True, self._tr.text("options." + key)) for key in _HIGH_RISK_FIELDS
            if values.get(key))

    def _show_profile_changes(self):
        if self._services is None or not hasattr(self, "_get_config"):
            return
        dialog = self._qt.QDialog(self._parent)
        dialog.setWindowTitle(self._tr.text("options.changes_title"))
        layout = self._qt.QVBoxLayout(dialog)
        layout.addWidget(self._qt.QLabel(self._tr.text(
            "options.changes_baseline", baseline=self._profile_baseline_label)))
        from ui.profile_compare import normalized_profile_values, profile_runtime_fields
        from app.profiles import Profile

        config = self._get_config()
        preferred_values = self.preference_values()
        preferred_profile = self._profile_for_values(
            config, preferred_values, preserve_disabled=True)
        effective_profile = self._profile_for_values(config, self.values())
        saved_values = normalized_profile_values(self._services.active)
        current_values = normalized_profile_values(preferred_profile)
        effective_values = normalized_profile_values(effective_profile)
        names = profile_runtime_fields()
        table = self._qt.QTableWidget(len(names), 4, dialog)
        table.setHorizontalHeaderLabels([
            self._tr.text("options.change_field"),
            self._tr.text("options.change_saved"),
            self._tr.text("options.change_current"),
            self._tr.text("options.change_effective"),
        ])
        table.setWordWrap(True)
        header = table.horizontalHeader()
        resize_mode = getattr(self._qt.QHeaderView, "ResizeMode", self._qt.QHeaderView)
        header.setSectionResizeMode(getattr(resize_mode, "Stretch"))
        from ui.profile_window import _PROFILE_SUMMARY_KEYS, _profile_summary_value

        no_edit = enum_value(self._qt.QAbstractItemView, "NoEditTriggers")
        if no_edit is not None:
            table.setEditTriggers(no_edit)
        for row, name in enumerate(names):
            old, new = saved_values[name], current_values[name]
            key = _PROFILE_SUMMARY_KEYS.get(name, "options." + name)
            label = self._tr.text(key)
            if label == key:
                label = name
            try:
                old_display = _profile_summary_value(replace(Profile(), **{name: old}),
                                                     name, self._tr)
                new_display = _profile_summary_value(replace(Profile(), **{name: new}),
                                                     name, self._tr)
            except (AttributeError, TypeError, ValueError):
                old_display = _display_option_value(old, self._tr)
                new_display = _display_option_value(new, self._tr)
            values = (
                label,
                old_display,
                new_display,
                self._effective_display(
                    name, effective_values[name],
                    _profile_summary_value(replace(Profile(), **{name: effective_values[name]}),
                                           name, self._tr)
                    if hasattr(Profile, name) else _display_option_value(
                        effective_values[name], self._tr),
                    requested=new),
            )
            for column, value in enumerate(values):
                item = self._qt.QTableWidgetItem(value)
                item.setToolTip(value)
                table.setItem(row, column, item)
        close = self._qt.QPushButton(self._tr.text("common.close"))
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        scroll = self._qt.QScrollArea(dialog)
        scroll.setWidgetResizable(True)
        scroll.setWidget(table)
        scroll.setMinimumHeight(300)
        layout.insertWidget(1, scroll, 1)
        application = self._qt.QApplication.instance()
        screen = application.primaryScreen() if application is not None else None
        available = screen.availableGeometry() if screen is not None else None
        available_width = available.width() if available is not None else 1040
        available_height = available.height() if available is not None else 720
        dialog.resize(min(1040, available_width), min(680, available_height))
        dialog.change_table = table
        exec_dialog(dialog)

    def _profile_for_values(self, config, values, *, preserve_disabled=False):
        try:
            return self._services.current_profile(config, values)
        except ValueError:
            # A display snapshot may intentionally retain force-pivot preferences
            # for a direction where the runtime control is disabled. Build it from
            # the validated effective profile, then restore only canonical fields.
            effective = self._services.current_profile(config, self.values())
            if not preserve_disabled:
                return effective
            preferred = self.preference_values()
            overrides = {
                "convert_metadata": preferred.get("include_metadata", effective.convert_metadata),
                "force_pivot": preferred.get("force_pivot", effective.force_pivot),
                "pivot_chain": preferred.get("pivot_chain", effective.pivot_chain),
            }
            return replace(effective, **overrides)

    def _effective_display(self, name, value, normal_display, *, requested=None):
        config = self._get_config() if hasattr(self, "_get_config") else "s2t"
        enablement = option_enablement(str(config), {
            **self.values(), "metadata_available": self._metadata_available,
        })
        unavailable_reason = None
        if name in {"convert_metadata", "include_metadata"} and not self._metadata_available:
            unavailable_reason = "options.metadata_unavailable"
        elif name in {"force_pivot", "pivot_chain"} and not enablement.get(name, False):
            unavailable_reason = "options.force_pivot_unavailable"
        elif name in {"language_preset", "language_region"} and not enablement.get(name, False):
            unavailable_reason = "options.language_not_effective"
        if unavailable_reason or (requested is not None and requested != value):
            unavailable_reason = unavailable_reason or "options.disabled_by_scope"
            reason = (self._tr.text(unavailable_reason, config=str(config))
                      if unavailable_reason == "options.force_pivot_unavailable"
                      else self._tr.text(unavailable_reason))
            return self._tr.text("options.not_effective_reason",
                                 value=normal_display,
                                 reason=reason)
        return normal_display

    def ui_state(self):
        return {"run_options_advanced_expanded": self._advanced_expanded}

    def retranslate(self):
        """Refresh this panel's labels after its shared translator changes."""
        for name, control in self.checks.items():
            control.setText(self._tr.text("options." + name))
        for name, label in self.combo_labels.items():
            label.setText(self._tr.text("options." + name))
        for name, combo in self.combos.items():
            if name == "pivot_chain":
                continue
            selected = combo.currentData()
            blocked = combo.blockSignals(True)
            try:
                combo.clear()
                for value in self._combo_values[name]:
                    combo.addItem(self._tr.text("options." + (value or "no_region")), value)
            finally:
                combo.blockSignals(blocked)
            index = combo.findData(selected)
            if index >= 0:
                combo.setCurrentIndex(index)
        self.documents_group.setTitle(self._tr.text("options.documents"))
        for group, key in (*self._option_groups, *self._named_groups):
            group.setTitle(self._tr.text(key))
        self.language_note.setText(self._tr.text("options.language_note"))
        self.tool_button.setText(self._tr.text("settings.tools"))
        for name, action in self._tool_actions.items():
            action.setText(self._tr.text("settings." + name))
        self.advanced_button.setText(self._tr.text("options.advanced"))
        self.view_changes_button.setText(self._tr.text("options.view_changes"))
        for button, name in self._profile_buttons:
            button.setText(self._tr.text("settings." + name))
        if hasattr(self, "ruleset_button"):
            self.ruleset_button.setText(self._tr.text("settings.rules"))
        self.update_enablement()


    def _tool(self, name):
        from app.errors import RuleConflictError
        from app.settings import profile_options
        try:
            config = self._get_config()
            if name == "profiles":
                profile = self._services.pick_profile(config, self.values(), self._tr)
                if profile is not None:
                    validate_profile = getattr(self._services, "validate_profile", None)
                    if callable(validate_profile):
                        profile = validate_profile(profile)
                    values = profile_options(profile)
                    values["language_metadata"] = normalize_language_mode(
                        values.get("language_metadata", "keep"))
                    # Validate the profile before touching the active settings.
                    self._set_config(profile.conversion)
                    self._updating = True
                    try:
                        self._initial = values
                        for key, control in self.checks.items():
                            control.setChecked(bool(values.get(key, False)))
                        for key, combo in self.combos.items():
                            value = (_pivot_chain_key(values.get(key, ())) if key == "pivot_chain"
                                     else values.get(key, "keep"))
                            index = combo.findData(value)
                            if index >= 0:
                                combo.setCurrentIndex(index)
                            elif key == "pivot_chain" and value:
                                self._preferred_pivot_chain = value
                    finally:
                        self._updating = False
                    commit_profile = getattr(self._services, "commit_profile", None)
                    if callable(commit_profile):
                        commit_profile(profile)
                    elif hasattr(self._services, "active"):
                        self._services.active = profile
                    self.update_enablement(profile.conversion)
            elif name == "save_profile":
                self._services.save_profile(config, self.values(), self._tr, self._qt, self._parent)
                self.update_enablement(config)
            elif name == "rules":
                self._services.edit_rules(
                    config, self._tr, self._qt, self._parent, run_options=self.values())
                self.update_enablement(config)
            else:
                self._services.open_tool(name, self._tr, self._qt, self._parent)
            callback = self._summary_changed_callback
            if callable(callback):
                callback()
        except (ValueError, OSError, RuleConflictError) as exc:
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


__all__ = ["ConfigurationChoice", "RunOptionsPanel", "option_enablement"]


class ConfigurationChoice(str):
    """Keep the historical config string API while carrying frozen options."""

    def __new__(cls, config, options, *, preference_options=None):
        from types import MappingProxyType

        instance = super().__new__(cls, config)
        instance.options = MappingProxyType(dict(options))
        instance.preference_options = MappingProxyType(
            dict(options if preference_options is None else preference_options))
        return instance


def _display_option_value(value, translator):
    if isinstance(value, bool):
        return translator.text("options.enabled" if value else "options.disabled")
    if isinstance(value, (tuple, list)):
        return ", ".join(str(item) for item in value) or "—"
    return str(value) if value not in (None, "") else "—"
