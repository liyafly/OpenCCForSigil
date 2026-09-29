from types import SimpleNamespace

from opencc_backend.configs import JIEBA_CONFIG_BY_BASE, SUPPORTED_CONFIGS
from tests.support import fake_qt
from ui.preview_window import _ConversionConfigDialog


class Translator:
    def text(self, key, **values):
        if key == "config.jieba_unavailable_tooltip":
            key = "Jieba check failed: {reason}"
        return key.format(**values)


class Control:
    def __init__(self, value=None):
        self.value = value
        self.enabled = True
        self.tooltip = ""
        self.text = ""
        self.visible = True

    def currentData(self):
        return self.value

    def isChecked(self):
        return bool(self.value)

    def setChecked(self, value):
        self.value = bool(value)

    def setEnabled(self, value):
        self.enabled = value

    def setToolTip(self, value):
        self.tooltip = value

    def setText(self, value):
        self.text = value

    def setVisible(self, value):
        self.visible = bool(value)

    def isVisible(self):
        return self.visible


class Probe:
    def __init__(self, state, reason=None):
        self.state = state
        self.reason = reason

    def jieba_probe_state(self):
        return self.state, self.reason, 300.0 if self.state != "pending" else None

    def available_configs_nonblocking(self):
        return SUPPORTED_CONFIGS if self.state == "available" else tuple(
            config for config in SUPPORTED_CONFIGS if not config.endswith("_jieba"))


def _dialog(probe, *, preferred_jieba=True):
    dialog = object.__new__(_ConversionConfigDialog)
    dialog._qt = SimpleNamespace(
        QMessageBox=SimpleNamespace(information=lambda *args: setattr(dialog, "details", args))
    )
    dialog.dialog = object()
    dialog._jieba_probe = probe
    dialog._jieba_configs = {}
    dialog._translator = Translator()
    dialog._probe_error = None
    dialog._probe_state = "pending"
    dialog._default_base = "s2t"
    dialog._preferred_jieba = preferred_jieba
    dialog._direction_reselected = False
    dialog._jieba_auto_checked = False
    dialog._updating_jieba = False
    dialog.combo = Control("s2t")
    dialog.jieba_checkbox = Control(False)
    dialog.jieba_status = Control()
    dialog._completion_enabled_callback = None
    dialog.options_panel = SimpleNamespace(update_enablement=lambda _config: None)
    return dialog


def _full_dialog(probe):
    jieba_configs = {
        base: config for base, config in JIEBA_CONFIG_BY_BASE.items() if config in SUPPORTED_CONFIGS
    }
    return _ConversionConfigDialog(
        fake_qt.make(),
        SUPPORTED_CONFIGS,
        "s2t_jieba",
        jieba_configs,
        translator=Translator(),
        jieba_probe=probe,
        embedded=True,
    )


def test_pending_probe_disables_preferred_jieba_and_success_restores_it():
    probe = Probe("pending")
    dialog = _dialog(probe)

    dialog._poll_jieba_probe()
    assert not dialog.jieba_checkbox.enabled
    assert not dialog._continue_is_allowed()
    assert dialog.jieba_status.text == "config.jieba_checking"

    probe.state = "available"
    dialog._poll_jieba_probe()

    assert dialog.jieba_checkbox.enabled
    assert dialog.jieba_checkbox.isChecked()
    assert dialog._continue_is_allowed()
    assert dialog._get_config() == "s2t_jieba"


def test_not_started_probe_disables_preferred_jieba_until_a_result_exists():
    dialog = _dialog(Probe("not_started"))

    dialog._poll_jieba_probe()

    assert not dialog.jieba_checkbox.enabled
    assert not dialog._continue_is_allowed()
    assert dialog.jieba_status.text == "config.jieba_checking"


def test_unavailable_preferred_jieba_explains_block_in_status_tooltip():
    probe = Probe("unavailable", "native library requires a newer operating system")
    dialog = _dialog(probe)

    dialog._poll_jieba_probe()
    assert not dialog.jieba_checkbox.enabled
    assert not dialog._continue_is_allowed()
    assert dialog.jieba_checkbox.isVisible()
    assert dialog.jieba_status.isVisible()
    assert probe.reason in dialog.jieba_checkbox.tooltip
    assert probe.reason in dialog.jieba_status.tooltip

    dialog.combo.value = "t2s"
    dialog._direction_changed()
    assert dialog._continue_is_allowed()


def test_unavailable_jieba_without_preference_is_hidden():
    dialog = _dialog(
        Probe("unavailable", "native library requires a newer operating system"),
        preferred_jieba=False,
    )

    dialog._poll_jieba_probe()

    assert not dialog.jieba_checkbox.isVisible()
    assert not dialog.jieba_status.isVisible()


def test_user_can_uncheck_preferred_jieba():
    dialog = _full_dialog(Probe("available"))

    assert dialog.jieba_checkbox.isChecked()
    dialog.jieba_checkbox.setChecked(False)

    assert not dialog.jieba_checkbox.isChecked()
    assert dialog._get_config() == "s2t"


def test_preferred_jieba_is_checked_once_when_probe_finishes():
    probe = Probe("pending")
    dialog = _full_dialog(probe)
    assert dialog._probe_timer.isActive()

    probe.state = "available"
    dialog._poll_jieba_probe()
    assert dialog.jieba_checkbox.isChecked()
    assert not dialog._probe_timer.isActive()

    dialog.jieba_checkbox.setChecked(False)
    dialog._poll_jieba_probe()

    assert not dialog.jieba_checkbox.isChecked()
    assert dialog._get_config() == "s2t"


def test_reject_stops_jieba_probe_timer():
    dialog = _full_dialog(Probe("pending"))
    assert dialog._probe_timer.isActive()

    dialog.dialog.reject()

    assert not dialog._probe_timer.isActive()


def test_conversion_direction_label_is_buddied_to_its_combo():
    dialog = _ConversionConfigDialog(
        fake_qt.make(),
        ("s2t", "t2s"),
        "s2t",
        {},
        translator=Translator(),
        embedded=True,
    )

    assert dialog.direction_label.buddy() is dialog.combo


def test_jieba_details_button_is_removed_and_failure_reason_is_available_in_tooltip():
    dialog = _full_dialog(Probe("available"))
    assert not hasattr(dialog, "jieba_details_button")

    failed_dialog = _full_dialog(Probe("unavailable", "native probe failed"))

    assert not hasattr(failed_dialog, "jieba_details_button")
    assert "native probe failed" in failed_dialog.jieba_status.toolTip()
