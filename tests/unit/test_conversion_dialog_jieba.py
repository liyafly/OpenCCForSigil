from types import SimpleNamespace

from opencc_backend.configs import SUPPORTED_CONFIGS
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


class Probe:
    def __init__(self, state, reason=None):
        self.state = state
        self.reason = reason

    def jieba_probe_state(self):
        return self.state, self.reason, 300.0 if self.state != "pending" else None

    def available_configs_nonblocking(self):
        return SUPPORTED_CONFIGS if self.state == "available" else tuple(
            config for config in SUPPORTED_CONFIGS if not config.endswith("_jieba"))


def _dialog(probe):
    dialog = object.__new__(_ConversionConfigDialog)
    dialog._qt = SimpleNamespace(QMessageBox=SimpleNamespace(
        information=lambda *args: setattr(dialog, "details", args)))
    dialog.dialog = object()
    dialog._jieba_probe = probe
    dialog._jieba_configs = {}
    dialog._translator = Translator()
    dialog._probe_error = None
    dialog._probe_state = "pending"
    dialog._default_base = "s2t"
    dialog._preferred_jieba = True
    dialog._direction_reselected = False
    dialog._updating_jieba = False
    dialog.combo = Control("s2t")
    dialog.jieba_checkbox = Control(False)
    dialog.jieba_status = Control()
    dialog.jieba_details_button = Control()
    dialog.continue_button = Control(True)
    dialog.options_panel = SimpleNamespace(update_enablement=lambda _config: None)
    return dialog


def test_pending_probe_disables_preferred_jieba_and_success_restores_it():
    probe = Probe("pending")
    dialog = _dialog(probe)

    dialog._poll_jieba_probe()
    assert not dialog.jieba_checkbox.enabled
    assert not dialog.continue_button.enabled
    assert dialog.jieba_status.text == "config.jieba_checking"

    probe.state = "available"
    dialog._poll_jieba_probe()

    assert dialog.jieba_checkbox.enabled
    assert dialog.jieba_checkbox.isChecked()
    assert dialog.continue_button.enabled
    assert dialog._get_config() == "s2t_jieba"


def test_not_started_probe_disables_preferred_jieba_until_a_result_exists():
    dialog = _dialog(Probe("not_started"))

    dialog._poll_jieba_probe()

    assert not dialog.jieba_checkbox.enabled
    assert not dialog.continue_button.enabled
    assert dialog.jieba_status.text == "config.jieba_checking"


def test_failed_preferred_probe_requires_direction_reselection_and_shows_reason():
    probe = Probe("unavailable", "native library requires a newer operating system")
    dialog = _dialog(probe)

    dialog._poll_jieba_probe()
    assert not dialog.jieba_checkbox.enabled
    assert not dialog.continue_button.enabled
    assert probe.reason in dialog.jieba_checkbox.tooltip
    assert dialog.jieba_details_button.enabled

    dialog._show_jieba_details()
    assert probe.reason in dialog.details[-1]

    dialog.combo.value = "t2s"
    dialog._direction_changed()
    assert dialog.continue_button.enabled
