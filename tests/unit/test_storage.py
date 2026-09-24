import json
import os
from types import SimpleNamespace

import pytest

from app.errors import StorageError
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


def test_preferences_write_removes_temporary_file_when_replace_fails(tmp_path, monkeypatch):
    store = UserDataStore(tmp_path / "user-data")

    def fail_replace(_source, _destination):
        raise OSError("simulated replace failure")

    monkeypatch.setattr("sigil.storage.os.replace", fail_replace)
    with pytest.raises(StorageError, match="could not write JSON storage"):
        store.save_preferences({"schema_version": 1, "language": "zh-Hans"})

    assert not tuple(store.paths.root.glob("preferences.*.tmp"))


def test_consecutive_preferences_saves_use_distinct_temporary_files(tmp_path, monkeypatch):
    store = UserDataStore(tmp_path / "user-data")
    real_replace = os.replace
    temporary_paths = []

    def record_replace(source, destination):
        temporary_paths.append(source)
        real_replace(source, destination)

    monkeypatch.setattr("sigil.storage.os.replace", record_replace)
    store.save_preferences({"schema_version": 1, "language": "en"})
    store.save_preferences({"schema_version": 1, "language": "zh-Hant"})

    assert len(temporary_paths) == 2
    assert temporary_paths[0] != temporary_paths[1]
    assert all(path.name.startswith("preferences.") and path.suffix == ".tmp"
               for path in temporary_paths)
    assert all(not path.exists() for path in temporary_paths)
    assert json.loads(store.paths.preferences.read_text(encoding="utf-8"))["language"] == "zh-Hant"
