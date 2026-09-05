from types import SimpleNamespace

from sigil.storage import UserDataStore, resolve_user_data_dir


def test_sigil_support_directory_has_priority(tmp_path):
    bk = SimpleNamespace(_w=SimpleNamespace(usrsupdir=str(tmp_path)))
    assert resolve_user_data_dir(bk) == tmp_path / "plugins_prefs" / "OpenCCForSigil"


def test_storage_layout_and_preferences_are_schema_aware(tmp_path):
    store = UserDataStore(tmp_path / "user-data")
    paths = store.ensure_layout()
    assert paths.logs.is_dir()
    assert store.load_preferences({"schema_version": 1, "last_profile_id": "conservative"})[
        "schema_version"
    ] == 1
