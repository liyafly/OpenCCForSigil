import json

from app.profiles import Profile, ProfileStore
from app.settings import RunSettings
from logging_ext.history import HistoryStore
from rules.store import RuleStore
from sigil.storage import UserDataStore
from types import SimpleNamespace
from ui.history_window import backup_and_rebuild_history


def _store(root):
    storage = UserDataStore(root)
    storage.ensure_layout()
    return storage


def test_corrupt_preferences_are_quarantined_and_noticed_once(tmp_path):
    storage = _store(tmp_path)
    original = "{ definitely not JSON"
    storage.paths.preferences.write_text(original, encoding="utf-8")

    values = storage.load_preferences(default={"schema_version": 1, "ui": {}})

    backups = tuple(tmp_path.glob("preferences.json.corrupt-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == original
    assert values == {"schema_version": 1, "ui": {}}
    assert storage.take_recovery_notice() == ("preferences_corrupt", backups[0].name)
    assert storage.take_recovery_notice() is None


def test_future_preferences_are_read_only_and_unchanged(tmp_path):
    storage = _store(tmp_path)
    original = '{"schema_version": 9, "ui": {"language": "en"}}\n'
    storage.paths.preferences.write_text(original, encoding="utf-8")
    before = storage.paths.preferences.stat().st_mtime_ns

    storage.load_preferences()
    updated = storage.update_preferences({
        "profile_id": None,
        "ui": {"run_options_advanced_expanded": True},
    })

    assert storage.read_only_preferences
    assert storage.paths.preferences.read_text(encoding="utf-8") == original
    assert storage.paths.preferences.stat().st_mtime_ns == before
    assert not tuple(tmp_path.glob("preferences.json.corrupt-*"))
    assert storage.take_recovery_notice() == ("preferences_future_schema", "9")
    assert updated["ui"] == {
        "language": "en", "run_options_advanced_expanded": True,
    }
    assert storage.load_preferences() == updated


def test_update_preferences_merges_fresh_disk_fields_and_nested_ui_values(tmp_path):
    storage = _store(tmp_path)
    storage.save_preferences({
        "schema_version": 1,
        "ui": {"language": "en", "conversion_dialog_size": [700, 500]},
        "checkpoint_notice": True,
    })
    stale = storage.load_preferences()
    storage.paths.preferences.write_text(json.dumps({
        "schema_version": 1,
        "ui": {
            "language": "zh-Hans", "conversion_dialog_size": [800, 600],
            "run_options_advanced_expanded": True,
        },
        "checkpoint_notice": False,
        "external_value": "fresh",
    }), encoding="utf-8")

    updated = storage.update_preferences({
        "ui": {"language": "zh-Hant"}, "last_conversion_config": "s2tw",
    })

    assert stale["ui"]["conversion_dialog_size"] == [700, 500]
    assert updated["ui"] == {
        "language": "zh-Hant", "conversion_dialog_size": [800, 600],
        "run_options_advanced_expanded": True,
    }
    assert updated["checkpoint_notice"] is False
    assert updated["external_value"] == "fresh"
    assert updated["last_conversion_config"] == "s2tw"


def test_missing_or_corrupt_active_profile_falls_back_and_clears_preference(tmp_path):
    storage = _store(tmp_path)
    profile_path = storage.paths.profiles / "broken.json"
    profile_path.write_text("not json", encoding="utf-8")
    adapter = SimpleNamespace()
    settings = RunSettings(
        storage, adapter, {"profile_id": "broken"},
        language="en", session_id="test-session")

    assert settings.active.id == "conservative"
    assert settings.clear_profile_preference
    assert settings.recovery_notice[0] == "profile_recovered"
    backup = storage.paths.profiles / settings.recovery_notice[1]
    assert backup.read_text(encoding="utf-8") == "not json"
    assert not profile_path.exists()


def test_future_profile_schema_is_preserved_and_selection_is_retained(tmp_path):
    storage = _store(tmp_path)
    path = storage.paths.profiles / "future.json"
    original = '{"schema_version": 2, "id": "future", "conversion": "s2tw"}\n'
    path.write_text(original, encoding="utf-8")
    before = path.stat().st_mtime_ns

    settings = RunSettings(
        storage, SimpleNamespace(), {"profile_id": "future"},
        language="en", session_id="test-session")

    assert settings.active.id == "conservative"
    assert settings.preserve_profile_preference
    assert not settings.clear_profile_preference
    assert storage.paths.profiles.joinpath("future.json").read_text(encoding="utf-8") == original
    assert path.stat().st_mtime_ns == before
    assert not tuple(storage.paths.profiles.glob("*.corrupt-*"))
    assert settings.take_recovery_notices() == (("profile_future_schema", "future.json"),)


def test_future_ruleset_schema_is_preserved_and_not_reported_as_corrupt(tmp_path):
    storage = _store(tmp_path)
    ProfileStore(storage.paths.profiles).save(
        Profile(id="custom", name="Custom", ruleset_ids=("newer",)))
    path = storage.paths.rules / "newer.json"
    original = '{"schema_version": 2, "id": "newer", "rules": []}\n'
    path.write_text(original, encoding="utf-8")
    before = path.stat().st_mtime_ns

    settings = RunSettings(
        storage, SimpleNamespace(), {"profile_id": "custom"},
        language="en", session_id="test-session")

    assert settings.active.ruleset_ids == ()
    assert path.read_text(encoding="utf-8") == original
    assert path.stat().st_mtime_ns == before
    assert not tuple(storage.paths.rules.glob("*.corrupt-*"))
    assert settings.take_recovery_notices() == (("rulesets_future_schema", "newer"),)


def test_profile_and_ruleset_lists_skip_corrupt_files_and_report_names(tmp_path):
    profiles = ProfileStore(tmp_path / "profiles")
    profiles.save(Profile(id="valid", name="Valid"))
    (tmp_path / "profiles" / "broken.json").write_text("[]", encoding="utf-8")
    profile_items, profile_errors = profiles.load_all()
    assert tuple(item.id for item in profile_items) == ("valid",)
    assert tuple(name for name, _message in profile_errors) == ("broken.json",)

    rules = RuleStore(tmp_path / "rules")
    rules.directory.mkdir(parents=True)
    (rules.directory / "broken.json").write_text("{", encoding="utf-8")
    rule_items, rule_errors = rules.list()
    assert rule_items == ()
    assert tuple(name for name, _message in rule_errors) == ("broken.json",)


def test_corrupt_or_missing_active_rulesets_are_backed_up_and_reported(tmp_path):
    storage = _store(tmp_path)
    ProfileStore(storage.paths.profiles).save(
        Profile(id="custom", name="Custom", ruleset_ids=("broken", "missing")))
    broken = storage.paths.rules / "broken.json"
    broken.write_text("not json", encoding="utf-8")

    settings = RunSettings(
        storage, SimpleNamespace(), {"profile_id": "custom"},
        language="en", session_id="test-session")

    assert settings.active.ruleset_ids == ()
    assert settings.take_missing_rulesets_notice() == ("broken", "missing")
    assert not broken.exists()
    backups = tuple(storage.paths.rules.glob("broken.json.corrupt-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "not json"
    assert settings.take_recovery_notices() == (
        ("rulesets_recovered", backups[0].name),
    )


def test_history_recovery_preserves_corrupt_index_and_rebuilds_empty_store(tmp_path):
    history = tmp_path / "history"
    history.mkdir()
    index = history / "index.json"
    index.write_text("broken history", encoding="utf-8")

    backup = backup_and_rebuild_history(history)

    assert backup.read_text(encoding="utf-8") == "broken history"
    assert HistoryStore(history).load() == []
    assert json.loads(index.read_text(encoding="utf-8")) == {
        "schema_version": 1, "sessions": []}
