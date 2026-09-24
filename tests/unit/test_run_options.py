from types import SimpleNamespace

import pytest

from app.settings import RunSettings
from app import settings as settings_module
from app.profiles import Profile
from opencc_backend.configs import V1_CONFIGS
from tests.support.fake_qt import make as make_fake_qt
from ui.i18n import Translator
from ui.run_options import (
    RunOptionsPanel,
    _decode_pivot_chain,
    _pivot_chain_key,
    option_enablement,
)
from ui.preview_window import _ConversionConfigDialog


def test_option_enablement_truth_table():
    cases = (
        ("s2t", {"force_pivot": False, "language_metadata": "keep"},
         {"include_nav": True, "force_pivot": True, "pivot_chain": False, "language_preset": False,
          "language_region": False, "include_metadata": True}),
        ("s2t", {"force_pivot": True, "language_metadata": "suggest"},
         {"include_nav": True, "force_pivot": True, "pivot_chain": True, "language_preset": True,
          "language_region": True, "include_metadata": True}),
        ("s2twp", {"force_pivot": True, "language_metadata": "force",
                    "language_preset": "bcp47"},
         {"include_nav": True, "force_pivot": True, "pivot_chain": True, "language_preset": True,
          "language_region": False, "include_metadata": True}),
        ("t2s", {"force_pivot": True, "language_metadata": "suggest"},
         {"include_nav": True, "force_pivot": True, "pivot_chain": True, "language_preset": True,
          "language_region": False, "include_metadata": True}),
        ("tw2t", {"force_pivot": True, "language_metadata": "force"},
         {"include_nav": True, "force_pivot": False, "pivot_chain": False, "language_preset": True,
          "language_region": True, "include_metadata": True}),
        ("hk2t", {"force_pivot": False, "language_metadata": "suggest",
                   "language_preset": "legacy"},
         {"include_nav": True, "force_pivot": False, "pivot_chain": False, "language_preset": True,
          "language_region": True, "include_metadata": True}),
        ("s2t", {"force_pivot": False, "language_metadata": "force",
                  "language_preset": "bcp47"},
         {"include_nav": True, "force_pivot": True, "pivot_chain": False, "language_preset": True,
          "language_region": False, "include_metadata": True}),
        ("tw2sp", {"force_pivot": True, "metadata_available": False},
         {"include_nav": True, "force_pivot": False, "pivot_chain": False, "language_preset": False,
          "language_region": False, "include_metadata": False}),
        ("s2t", {"nav_available": False},
         {"include_nav": False, "force_pivot": True, "pivot_chain": False,
          "language_preset": False, "language_region": False, "include_metadata": True}),
    )
    for config, values, expected in cases:
        result = option_enablement(config, values)
        assert result == expected


def test_pivot_chain_profile_list_uses_string_item_key():
    assert _pivot_chain_key(["t2s", "s2tw"]) == "t2s>s2tw"
    assert _decode_pivot_chain("t2s>s2tw") == ("t2s", "s2tw")


def test_report_text_dialog_has_a_close_button(monkeypatch):
    qt = make_fake_qt()
    dialogs = []
    monkeypatch.setattr(settings_module, "exec_dialog", lambda dialog: dialogs.append(dialog))

    RunSettings.show_text("Report contents", "Report", qt, None)

    dialog = dialogs[0]
    button_box = dialog._layout.children[-1]
    close_button = button_box.button(qt.QDialogButtonBox.StandardButton.Close)
    assert close_button is not None
    close_button.clicked.emit()
    assert dialog.result == 1


class StatefulCombo:
    def __init__(self, value=None):
        self.items = []
        self.index = -1
        self.value = value
        self.enabled = True
        self.signals_blocked = False

    def currentData(self):
        if 0 <= self.index < len(self.items):
            return self.items[self.index][1]
        return self.value

    def clear(self):
        self.items.clear()
        self.index = -1

    def addItem(self, text, data):
        self.items.append((text, data))
        if self.index < 0:
            self.index = 0

    def findData(self, value):
        return next((index for index, item in enumerate(self.items) if item[1] == value), -1)

    def setCurrentIndex(self, value):
        self.index = value

    def setEnabled(self, value):
        self.enabled = value

    def blockSignals(self, value):
        old = self.signals_blocked
        self.signals_blocked = value
        return old


class StatefulCheck:
    def __init__(self, value=False):
        self.value = value
        self.enabled = True
        self.tooltip = ""

    def isChecked(self):
        return self.value

    def setChecked(self, value):
        self.value = value

    def setEnabled(self, value):
        self.enabled = value

    def setToolTip(self, value):
        self.tooltip = value


def test_profile_chain_list_loads_and_direction_filters_chains():
    panel = object.__new__(RunOptionsPanel)
    panel._initial = {"force_pivot": True, "pivot_chain": ["t2s", "s2tw"]}
    panel._preferred_pivot_chain = "t2s>s2tw"
    panel._metadata_available = True
    panel._nav_available = True
    panel._services = None
    panel._enablement = {}
    panel._updating = False
    panel._tr = SimpleNamespace(text=lambda key, **_values: key)
    panel._get_config = lambda: "s2tw"
    panel.checks = {
        "include_nav": StatefulCheck(True),
        "force_pivot": StatefulCheck(True),
        "include_metadata": StatefulCheck(False),
    }
    panel.combos = {
        "pivot_chain": StatefulCombo(),
        "language_metadata": StatefulCombo("keep"),
        "language_preset": StatefulCombo("legacy"),
        "language_region": StatefulCombo(""),
    }

    panel.update_enablement("s2tw")
    assert panel.values()["pivot_chain"] == ("t2s", "s2tw")

    panel.update_enablement("s2hk")
    visible_chains = [item[1] for item in panel.combos["pivot_chain"].items]
    assert visible_chains
    assert all(chain.split(">")[-1] == "s2hk" for chain in visible_chains)
    assert panel.values()["pivot_chain"] == ("t2s", "s2hk")


def _live_options_panel(initial=None, *, nav_available=True):
    qt = make_fake_qt()
    return RunOptionsPanel(
        qt, Translator("en"), qt.QVBoxLayout(), initial=initial,
        metadata_available=True, nav_available=nav_available,
    )


def test_realistic_combo_signals_do_not_replace_saved_pivot_chain():
    panel = _live_options_panel({
        "force_pivot": True,
        "pivot_chain": ["s2twp", "t2s"],
    })

    panel.update_enablement("t2s")

    assert panel.values()["pivot_chain"] == ("s2twp", "t2s")


@pytest.mark.parametrize(
    ("direction", "chain"),
    (
        ("t2s", ("s2tw", "t2s")),
        ("t2s", ("s2twp", "t2s")),
        ("s2tw", ("t2s", "s2tw")),
        ("s2t", ("t2s", "s2t")),
    ),
)
def test_opening_dialog_preserves_saved_pivot_chain(direction, chain):
    dialog = _ConversionConfigDialog(
        make_fake_qt(), tuple(V1_CONFIGS), direction, {}, translator=Translator("en"),
        initial_options={"force_pivot": True, "pivot_chain": chain},
    )
    panel = dialog.options_panel

    assert panel.values()["pivot_chain"] == chain
    assert panel.preference_values()["pivot_chain"] == chain


def test_manual_pivot_chain_selection_survives_direction_changes():
    dialog = _ConversionConfigDialog(
        make_fake_qt(), tuple(V1_CONFIGS), "t2s", {}, translator=Translator("en"),
        initial_options={"force_pivot": True, "pivot_chain": ("s2tw", "t2s")},
    )
    panel = dialog.options_panel
    chain_combo = panel.combos["pivot_chain"]
    selected = chain_combo.findData("s2twp>t2s")
    assert selected >= 0
    chain_combo.setCurrentIndex(selected)

    dialog.combo.setCurrentIndex(dialog.combo.findData("s2t"))
    dialog.combo.setCurrentIndex(dialog.combo.findData("t2s"))

    assert panel.preference_values()["pivot_chain"] == ("s2twp", "t2s")


def test_profile_load_applies_direction_before_saved_disabled_options():
    profile = Profile(
        id="pivot-profile", name="Pivot", conversion="s2t", force_pivot=True,
        pivot_chain=("t2s", "s2t"),
    )
    panel = _live_options_panel({"conversion": "tw2t"})
    panel._services = SimpleNamespace(
        pick_profile=lambda *_args: profile,
        active=SimpleNamespace(id="active", ruleset_ids=()),
    )
    panel._get_config = lambda: "tw2t"
    config = {"value": "tw2t"}

    def set_config(value):
        config["value"] = value
        panel.update_enablement(value)

    panel._set_config = set_config
    panel._parent = None
    panel._update_profile_label = lambda _config: None
    panel.update_enablement("tw2t")
    assert not panel.checks["force_pivot"].isEnabled()

    panel._tool("profiles")

    assert config["value"] == "s2t"
    assert panel.checks["force_pivot"].isChecked()
    assert panel.values()["force_pivot"]
    assert panel.values()["pivot_chain"] == ("t2s", "s2t")


def test_nav_preference_survives_a_scope_without_navigation_document():
    panel = _live_options_panel({"include_nav": True}, nav_available=False)
    panel.update_enablement("s2t")

    assert not panel.checks["include_nav"].isEnabled()
    assert panel.checks["include_nav"].isChecked()
    assert panel.values()["include_nav"] is False
    assert panel.preference_values()["include_nav"] is True

    panel._nav_available = True
    panel.update_enablement("s2t")

    assert panel.checks["include_nav"].isEnabled()
    assert panel.checks["include_nav"].isChecked()
    assert panel.values()["include_nav"] is True


def test_jieba_configs_disable_force_pivot_with_a_specific_tooltip():
    panel = _live_options_panel({"force_pivot": True})

    panel.update_enablement("s2twp_jieba")

    assert not panel.checks["force_pivot"].isEnabled()
    assert not panel.values()["force_pivot"]
    assert not panel._enablement["pivot_chain"]
    assert panel.checks["force_pivot"].toolTip() == (
        "Force pivot is not supported for Jieba configurations.")


def test_nav_is_disabled_when_selected_scope_has_no_navigation_document():
    panel = object.__new__(RunOptionsPanel)
    panel._initial = {"conversion": "s2t", "force_pivot": False}
    panel._preferred_pivot_chain = ""
    panel._metadata_available = True
    panel._nav_available = False
    panel._services = None
    panel._enablement = {}
    panel._updating = False
    panel._tr = SimpleNamespace(text=lambda key, **_values: key)
    panel.checks = {
        "include_nav": StatefulCheck(True),
        "force_pivot": StatefulCheck(False),
        "include_metadata": StatefulCheck(False),
    }
    panel.combos = {
        "pivot_chain": StatefulCombo(),
        "language_metadata": StatefulCombo("keep"),
        "language_preset": StatefulCombo("legacy"),
        "language_region": StatefulCombo(""),
    }

    panel._update_enablement("s2t")

    assert not panel.checks["include_nav"].enabled
    assert panel.checks["include_nav"].value
    assert panel.values()["include_nav"] is False
    assert panel.preference_values()["include_nav"] is True
    assert panel.checks["include_nav"].tooltip == "options.nav_unavailable"


class Check:
    def __init__(self, value):
        self.value = value

    def isChecked(self):
        return self.value


class Combo:
    def __init__(self, value):
        self.value = value

    def currentData(self):
        return self.value


def test_values_only_returns_controls_and_profile_references():
    panel = object.__new__(RunOptionsPanel)
    panel.checks = {"force_pivot": Check(True), "convert_alt": Check(False)}
    panel.combos = {
        "language_metadata": Combo("force"),
        "pivot_chain": Combo("t2s>s2tw"),
    }
    panel._services = SimpleNamespace(
        active=SimpleNamespace(id="profile-1", ruleset_ids=("default", "mine")))
    panel._initial = {"scope": "all_xhtml", "attributes": ["title"], "segmentation": "mmseg"}
    panel._enablement = {"pivot_chain": True, "force_pivot": True}
    panel._metadata_available = True
    panel._nav_available = True

    values = panel.values()

    assert values["pivot_chain"] == ("t2s", "s2tw")
    assert values["profile_id"] == "profile-1"
    assert values["ruleset_ids"] == ["default", "mine"]
    assert not {"scope", "attributes", "segmentation"} & values.keys()


def test_current_profile_rebuilds_attributes_from_visible_checkboxes(tmp_path):
    storage = SimpleNamespace(paths=SimpleNamespace(
        root=tmp_path, profiles=tmp_path / "profiles", rules=tmp_path / "rules"))
    settings = RunSettings(
        storage, SimpleNamespace(), {}, language="en", session_id="test-session")
    settings.active = Profile(id="conservative", name="Conservative")

    current = settings.current_profile("s2t", {
        "convert_alt": False,
        "convert_title": True,
        "convert_aria_label": True,
        "attributes": ["alt"],
        "scope": "single",
        "segmentation": "stale",
    })

    assert current.attributes == ("title", "aria-label")
    assert current.convert_alt is False
    assert current.convert_title is True
    assert current.convert_aria_label is True


def test_profile_label_marks_changed_settings(tmp_path):
    storage = SimpleNamespace(paths=SimpleNamespace(
        root=tmp_path, profiles=tmp_path / "profiles", rules=tmp_path / "rules"))
    settings = RunSettings(
        storage, SimpleNamespace(), {}, language="en", session_id="test-session")
    panel = object.__new__(RunOptionsPanel)
    panel._services = settings
    panel._tr = SimpleNamespace(text=lambda key, **values: {
        "profile.default_name": "Conservative",
        "options.profile_modified": " (modified)",
        "options.current_profile": "Current: {name}{status}",
        "options.active_rulesets": "Rules: {ids}",
    }[key].format(**values))
    panel.profile_label = SimpleNamespace(setText=lambda value: setattr(panel, "label", value))
    panel.ruleset_label = SimpleNamespace(setText=lambda value: setattr(panel, "rules", value))
    panel.values = lambda: {"convert_alt": False, "ruleset_ids": ["default"]}

    panel._update_profile_label("s2t")

    assert panel.label == "Current: Conservative (modified)"


def test_profile_label_does_not_mark_an_untouched_profile_modified(tmp_path):
    from app.settings import profile_options

    storage = SimpleNamespace(paths=SimpleNamespace(
        root=tmp_path, profiles=tmp_path / "profiles", rules=tmp_path / "rules"))
    settings = RunSettings(
        storage, SimpleNamespace(), {}, language="en", session_id="test-session")
    panel = object.__new__(RunOptionsPanel)
    panel._services = settings
    panel._tr = SimpleNamespace(text=lambda key, **values: {
        "profile.default_name": "Conservative",
        "options.profile_modified": " (modified)",
        "options.current_profile": "Current: {name}{status}",
        "options.active_rulesets": "Rules: {ids}",
    }[key].format(**values))
    panel.profile_label = SimpleNamespace(setText=lambda value: setattr(panel, "label", value))
    panel.ruleset_label = SimpleNamespace(setText=lambda value: setattr(panel, "rules", value))
    panel.values = lambda: profile_options(settings.active)

    panel._update_profile_label(settings.active.conversion)

    assert panel.label == "Current: Conservative"


def test_profile_validation_failure_leaves_config_options_and_active_profile_unchanged(
        monkeypatch):
    import ui.run_options as run_options

    profile = Profile(
        id="new", name="New", conversion="t2s", convert_alt=False,
        ruleset_ids=("default",),
    )
    active = Profile(id="active", name="Active", conversion="s2t", convert_alt=True)
    panel = _live_options_panel({"conversion": "s2t", "convert_alt": True})

    def reject_profile(_profile):
        raise ValueError("bad profile")

    panel._services = SimpleNamespace(
        active=active,
        pick_profile=lambda *_args: profile,
        validate_profile=reject_profile,
    )
    state = {"config": "s2t"}
    panel._get_config = lambda: state["config"]
    panel._set_config = lambda value: state.update(config=value)
    panel._parent = None
    monkeypatch.setattr(run_options, "show_error_details", lambda *_args: None)

    panel._tool("profiles")

    assert state["config"] == "s2t"
    assert panel.checks["convert_alt"].isChecked()
    assert panel._services.active is active


def test_conversion_dialog_keeps_direction_panel_and_footer_in_order():
    qt = make_fake_qt()
    dialog = _ConversionConfigDialog(
        qt, ("s2t", "t2s"), "s2t", {}, translator=Translator("en"))
    outer = dialog.dialog._layout.children

    assert [type(item).__name__ for item in outer[:7]] == [
        "QLabel", "QLabel", "QComboBox", "QLabel", "QCheckBox", "QPushButton",
        "QScrollArea",
    ]
    footer = outer[7]
    assert footer is dialog.options_panel.tool_layout
    scroll_body = outer[6].widget()
    assert [type(item).__name__ for item in scroll_body._layout.children] == [
        "QHBoxLayout", "QHBoxLayout", "QGroupBox", "QToolButton", "QWidget",
    ]
    assert footer.children[0]._text == Translator("en").text("settings.tools")
    assert footer.children[-1] is dialog.button_box
    assert dialog.cancel_button.text() == Translator("en").text("common.cancel")


def test_save_profile_rejects_duplicate_names_case_insensitively(tmp_path):
    from app.settings import profile_options

    storage = SimpleNamespace(paths=SimpleNamespace(
        root=tmp_path, profiles=tmp_path / "profiles", rules=tmp_path / "rules"))
    settings = RunSettings(
        storage, SimpleNamespace(), {}, language="en", session_id="test-session")
    settings.profiles.save(Profile(id="existing", name="Mine"))
    warnings = []
    qt = SimpleNamespace(
        QInputDialog=SimpleNamespace(getText=lambda *_args: (" mine ", True)),
        QMessageBox=SimpleNamespace(warning=lambda *_args: warnings.append(_args[-1])),
    )

    settings.save_profile(
        "s2t", profile_options(settings.active), Translator("en"), qt, None)

    assert warnings == [Translator("en").text("settings.profile_duplicate")]
    assert [profile.id for profile in settings.profiles.load_all()[0]] == ["existing"]


def test_settings_windows_query_nonblocking_config_availability(tmp_path):
    calls = []

    class Backend:
        jieba_probe_pending = True

        def available_configs_nonblocking(self):
            calls.append("nonblocking")
            return {"s2t"}

        def available_configs(self):
            raise AssertionError("blocking config check was called")

    storage = SimpleNamespace(paths=SimpleNamespace(
        root=tmp_path, profiles=tmp_path / "profiles", rules=tmp_path / "rules"))
    settings = RunSettings(
        storage, SimpleNamespace(), {}, language="en", session_id="test-session")
    settings.backend = Backend()

    assert settings._available_config_options() == (("s2t",), True)
    assert calls == ["nonblocking"]


def test_report_export_exception_is_put_in_details_with_localized_summary(
        monkeypatch, tmp_path):
    import app.settings as settings_module
    from logging_ext import report as report_module

    storage = SimpleNamespace(paths=SimpleNamespace(
        root=tmp_path, profiles=tmp_path / "profiles", rules=tmp_path / "rules",
        exports=tmp_path / "exports"))
    settings = RunSettings(
        storage, SimpleNamespace(), {}, language="zh-Hans", session_id="test-session")
    details = []

    def fail_export(*_args, **_kwargs):
        raise OSError("raw export failure")

    monkeypatch.setattr(report_module, "export_markdown", fail_export)
    monkeypatch.setattr(settings_module, "show_error_details", lambda *args: details.append(args))
    qt = SimpleNamespace(QFileDialog=SimpleNamespace(
        getSaveFileName=lambda *_args: ("/tmp/report.md", "")))
    record = {"summary": {}, "commit_manifest": {}, "provenance": {}, "session_id": "session"}

    settings.export_report(record, False, None, Translator("zh-Hans"), qt, None)

    assert details[0][3] == Translator("zh-Hans").text("settings.export_failed")
    assert details[0][4] == "raw export failure"


def test_new_default_profile_name_uses_selected_ui_language(tmp_path):
    for language in ("zh-Hans", "zh-Hant", "en"):
        storage = SimpleNamespace(paths=SimpleNamespace(
            root=tmp_path / language, profiles=tmp_path / language / "profiles",
            rules=tmp_path / language / "rules"))
        settings = RunSettings(
            storage, SimpleNamespace(), {}, language=language, session_id="test-session")

        assert settings.active.id == "conservative"
        assert settings.active.name == Translator(language).text("profile.default_name")


def test_advanced_options_fold_state_is_saved_in_ui_preferences():
    class Content:
        visible = None

        def setVisible(self, value):
            self.visible = value

    panel = object.__new__(RunOptionsPanel)
    panel._qt = SimpleNamespace(Qt=SimpleNamespace())
    panel._ui_preferences = {}
    panel.advanced_content = Content()
    panel.advanced_button = SimpleNamespace()
    panel._advanced_toggled(True)

    assert panel.advanced_content.visible is True
    assert panel.ui_state() == {"run_options_advanced_expanded": True}


def test_export_preview_requires_a_bound_run_context(tmp_path):
    storage = SimpleNamespace(paths=SimpleNamespace(
        root=tmp_path, profiles=tmp_path / "profiles", rules=tmp_path / "rules"))
    settings = RunSettings(
        storage, SimpleNamespace(), {}, language="en", session_id="test-session")

    with pytest.raises(RuntimeError, match="not bound to an active profile and backend"):
        settings.export_preview((), (), False, None, None)


def test_settings_windows_use_nonblocking_configuration_availability():
    settings = object.__new__(RunSettings)
    calls = []

    def blocking_configs():
        raise AssertionError("UI must not wait for the Jieba probe")

    settings.backend = SimpleNamespace(
        available_configs=blocking_configs,
        available_configs_nonblocking=lambda: calls.append("nonblocking") or ("s2t",),
        jieba_probe_pending=True,
    )

    assert settings._available_config_options() == (("s2t",), True)
    assert calls == ["nonblocking"]
