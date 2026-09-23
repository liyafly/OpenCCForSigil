from types import SimpleNamespace

import pytest

from app.settings import RunSettings
from app.profiles import Profile
from ui.run_options import (
    RunOptionsPanel,
    _decode_pivot_chain,
    _pivot_chain_key,
    option_enablement,
)


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


class StatefulCombo:
    def __init__(self, value=None):
        self.items = []
        self.index = -1
        self.value = value
        self.enabled = True

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
    assert not panel.checks["include_nav"].value
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
        "options.profile_modified": " (modified)",
        "options.current_profile": "Current: {name}{status}",
        "options.active_rulesets": "Rules: {ids}",
    }[key].format(**values))
    panel.profile_label = SimpleNamespace(setText=lambda value: setattr(panel, "label", value))
    panel.ruleset_label = SimpleNamespace(setText=lambda value: setattr(panel, "rules", value))
    panel.values = lambda: {"convert_alt": False, "ruleset_ids": ["default"]}

    panel._update_profile_label("s2t")

    assert panel.label == "Current: Conservative (modified)"


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
