"""Conversion configuration page shown inside the scope dialog."""

from __future__ import annotations

from typing import Any

from opencc_backend.configs import (
    BASE_CONFIG_BY_JIEBA,
    JIEBA_CONFIG_BY_BASE,
)
from ui.i18n import (
    Translator,
    plugin_window_title,
    settings_error_message,
    show_error_details,
)


class _ConversionConfigDialog:
    def __init__(
        self,
        qt_widgets: Any,
        configs: tuple[str, ...],
        default_config: str,
        jieba_configs: dict[str, str],
        *,
        translator: Translator,
        jieba_probe=None,
        initial_options=None,
        metadata_available=True,
        services=None,
        ui_preferences=None,
        embedded=True,
        container=None,
        parent_dialog=None,
    ) -> None:
        self._qt = qt_widgets
        self._jieba_configs = jieba_configs
        self._translator = translator
        self._jieba_probe = jieba_probe
        self._ui_preferences = dict(ui_preferences or {})
        if not embedded:
            raise ValueError("Conversion configuration must be embedded in the scope chooser")
        self._probe_error = None
        self._probe_state = "not_started"
        self._default_base = BASE_CONFIG_BY_JIEBA.get(default_config, default_config)
        self._preferred_jieba = default_config in BASE_CONFIG_BY_JIEBA
        self._direction_reselected = not self._preferred_jieba
        self._jieba_auto_checked = False
        self._updating_jieba = False
        self.accepted = False
        self.selected_config = None
        self.dialog = parent_dialog or qt_widgets.QDialog()

        layout = qt_widgets.QVBoxLayout(container or self.dialog)
        self.explanation_label = qt_widgets.QLabel(
            self._translator.text("config.explanation"))
        self.explanation_label.setWordWrap(True)
        layout.addWidget(self.explanation_label)

        self.direction_label = qt_widgets.QLabel(
            self._translator.text("config.direction"))
        self.combo = qt_widgets.QComboBox()
        self.direction_label.setBuddy(self.combo)
        config_groups = (
            ("general", ("s2t", "t2s")),
            ("regional", ("s2tw", "s2twp", "s2hk", "s2hkp", "tw2s", "tw2sp",
                           "hk2s", "hk2sp", "t2tw", "t2hk", "tw2t", "hk2t")),
            ("japanese", ("t2jp", "jp2t")),
        )
        available = set(configs)
        groups_added = 0
        for _group, group_configs in config_groups:
            group_values = tuple(config for config in group_configs if config in available)
            if not group_values:
                continue
            if groups_added:
                insert_separator = getattr(self.combo, "insertSeparator", None)
                if callable(insert_separator):
                    insert_separator(self.combo.count())
            for config in group_values:
                label = self._translator.text(f"config.{config}")
                self.combo.addItem(label, config)
            groups_added += 1
        self.jieba_status = qt_widgets.QLabel()
        self.jieba_status.setWordWrap(True)
        layout.addWidget(self.jieba_status)
        self.jieba_checkbox = qt_widgets.QCheckBox(self._translator.text("config.jieba"))
        self.jieba_checkbox.setToolTip(self._translator.text("config.jieba_tooltip"))
        layout.addWidget(self.jieba_checkbox)
        from ui.run_options import RunOptionsPanel
        self.options_panel = RunOptionsPanel(
            qt_widgets, translator, layout, initial=initial_options,
            metadata_available=metadata_available,
            services=services, ui_preferences=self._ui_preferences,
        )
        self.options_panel.bind(self._get_config, self._set_config, self.dialog)

        self._completion_enabled_callback = None
        self.combo.currentIndexChanged.connect(self._direction_changed)
        self.jieba_checkbox.stateChanged.connect(self._update_jieba_state)
        selected_index = self.combo.findData(self._default_base)
        if selected_index >= 0:
            self.combo.setCurrentIndex(selected_index)
        self.jieba_checkbox.setChecked(
            default_config in self._jieba_configs.values())
        if self.jieba_checkbox.isChecked():
            self._jieba_auto_checked = True
        if self._jieba_probe is not None:
            self._poll_jieba_probe()
            if self._probe_state == "pending":
                timer_type = getattr(qt_widgets, "QTimer", None)
                if timer_type is not None:
                    self._probe_timer = timer_type(self.dialog)
                    self.dialog.finished.connect(self._stop_probe_timer)
                    self._probe_timer.setInterval(50)
                    self._probe_timer.timeout.connect(self._poll_jieba_probe)
                    self._probe_timer.start()
        else:
            self._probe_state = "available" if self._jieba_configs else "unavailable"
        self._update_jieba_state()

    def _get_config(self):
        base = str(self.combo.currentData())
        return self._jieba_configs.get(base, base) if self.jieba_checkbox.isChecked() else base

    def _set_config(self, config):
        base = BASE_CONFIG_BY_JIEBA.get(config, config)
        index = self.combo.findData(base)
        if index < 0 or (config != base and config not in self._jieba_configs.values()):
            raise ValueError("profile configuration is unavailable on this host")
        self.combo.setCurrentIndex(index)
        self.jieba_checkbox.setChecked(config != base)
        self._update_jieba_state()

    def _update_jieba_state(self) -> None:
        if self._updating_jieba:
            return
        self._updating_jieba = True
        try:
            self._apply_jieba_state()
        finally:
            self._updating_jieba = False

    def _apply_jieba_state(self) -> None:
        base_config = str(self.combo.currentData())
        plugin_config = self._jieba_configs.get(base_config)
        if self._probe_state in {"not_started", "pending"} or plugin_config is None:
            self.jieba_checkbox.setChecked(False)
            self.jieba_checkbox.setEnabled(False)
        else:
            self.jieba_checkbox.setEnabled(True)
        if self._probe_state in {"not_started", "pending"}:
            status = self._translator.text("config.jieba_checking")
        elif self._probe_state == "available":
            status = self._translator.text("config.jieba_available")
        else:
            status = self._translator.text("config.jieba_unavailable")
            if self._preferred_jieba and not self._direction_reselected:
                status += "\n" + self._translator.text("config.jieba_reselect")
        if self._probe_state == "available" and self._preferred_jieba \
                and not self._direction_reselected and base_config == self._default_base \
                and not self._jieba_auto_checked:
            self._jieba_auto_checked = True
            self.jieba_checkbox.setChecked(True)
        if self._probe_error:
            tooltip = self._translator.text(
                "config.jieba_unavailable_tooltip", reason=self._probe_error)
        else:
            tooltip = self._translator.text("config.jieba_tooltip")
        self.jieba_checkbox.setToolTip(tooltip)
        self.jieba_status.setToolTip(tooltip)
        self.jieba_status.setText(status)
        controls_visible = not (
            self._probe_state == "unavailable" and not self._preferred_jieba)
        self.jieba_checkbox.setVisible(controls_visible)
        self.jieba_status.setVisible(controls_visible)
        self.options_panel.update_enablement(self._get_config())
        callback = self._completion_enabled_callback
        if callable(callback):
            callback()

    def _direction_changed(self, *_args):
        if str(self.combo.currentData()) != self._default_base:
            self._direction_reselected = True
        self._update_jieba_state()

    def _poll_jieba_probe(self):
        state, reason, _elapsed_ms = self._jieba_probe.jieba_probe_state()
        self._probe_state = state
        self._probe_error = reason
        if state == "available":
            available = set(self._jieba_probe.available_configs_nonblocking())
            self._jieba_configs = {
                base: config for base, config in JIEBA_CONFIG_BY_BASE.items()
                if config in available
            }
        elif state == "unavailable":
            self._jieba_configs = {}
        self._update_jieba_state()
        if state != "pending":
            self._stop_probe_timer()

    def _stop_probe_timer(self):
        timer = getattr(self, "_probe_timer", None)
        if timer is not None:
            timer.stop()

    def _accept(self, *, close=True) -> None:
        from app.errors import RuleConflictError
        from transforms.language_tags import target_language
        from ui.run_options import ConfigurationChoice

        base_config = str(self.combo.currentData())
        config = (
            self._jieba_configs[base_config]
            if self.jieba_checkbox.isChecked() and base_config in self._jieba_configs
            else base_config
        )
        options = self.options_panel.values()
        preference_options = self.options_panel.preference_values()
        try:
            self.options_panel.validate(config)
            target_language(config, options["language_metadata"], options["language_preset"],
                            options["language_region"])
        except (ValueError, RuleConflictError) as exc:
            show_error_details(
                self._qt, self.dialog, self._translator.text("config.title"),
                settings_error_message(self._translator, exc), str(exc),
            )
            return
        self._stop_probe_timer()
        self.selected_config = ConfigurationChoice(
            config, options, preference_options=preference_options)
        self.accepted = True
        if close:
            self.dialog.accept()

    def _retranslate(self) -> None:
        """Refresh visible text after the shared language selector changes."""
        self.dialog.setWindowTitle(plugin_window_title(
            self._translator, self._translator.text("main.title")))
        self.explanation_label.setText(self._translator.text("config.explanation"))
        self.direction_label.setText(self._translator.text("config.direction"))
        selected = self.combo.currentData()
        blocked = self.combo.blockSignals(True)
        try:
            for index in range(self.combo.count()):
                config = self.combo.itemData(index)
                if config:
                    self.combo.setItemText(index, self._translator.text(f"config.{config}"))
        finally:
            self.combo.blockSignals(blocked)
        selected_index = self.combo.findData(selected)
        if selected_index >= 0:
            self.combo.setCurrentIndex(selected_index)
        self.jieba_checkbox.setText(self._translator.text("config.jieba"))
        self.jieba_checkbox.setToolTip(self._translator.text("config.jieba_tooltip"))
        self.options_panel.retranslate()
        self._apply_jieba_state()

    def _continue_is_allowed(self) -> bool:
        if self._preferred_jieba and self._probe_state in {"not_started", "pending"}:
            return False
        return not (self._preferred_jieba and self._probe_state == "unavailable"
                    and not self._direction_reselected)
