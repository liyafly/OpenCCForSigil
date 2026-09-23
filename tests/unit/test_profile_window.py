from types import SimpleNamespace

from app.profiles import Profile, ProfileStore
from ui.profile_window import ProfileManagerDialog


class ProfileList:
    def currentRow(self):
        return 0


class Button:
    def __init__(self):
        self.enabled = True

    def setEnabled(self, enabled):
        self.enabled = enabled


class Check:
    def __init__(self, checked=False):
        self.checked = checked

    def isChecked(self):
        return self.checked

    def setChecked(self, checked):
        self.checked = checked


class Dialog:
    def __init__(self):
        self.accepted = False

    def accept(self):
        self.accepted = True


def _manager(profiles, store, *, active=None, current=None, selected_id=None,
             input_name=("", False), answer=0, on_delete=None):
    manager = object.__new__(ProfileManagerDialog)
    manager._profiles = list(profiles)
    manager._store = store
    manager._on_delete = on_delete
    manager._labels = {
        "title": "Profiles", "use": "Use", "rename": "Rename", "copy": "Copy",
        "delete": "Delete", "from_current": "From current settings", "close": "Close",
        "summary": "Summary", "conversion": "Direction", "rules": "Rule sets",
        "options": "Options", "jieba": "Advanced Jieba", "unavailable": "unavailable",
        "ask_name": "Profile name", "duplicate_name": "duplicate", "invalid_name": "empty",
        "confirm_delete": "Delete {name}?", "delete_modified": "modified",
        "copied": " copy", "skipped_files": "skipped: {files}", "not_selected": "select",
    }
    manager._available_config_ids = set()
    manager._jieba_pending = False
    manager._available_rulesets = ("default", "mine")
    manager._selected_id = selected_id
    manager._current_profile = current or (profiles[0] if profiles else None)
    manager._active_profile = active
    manager.profile_list = ProfileList()
    manager.rules_checks = {"default": Check(), "mine": Check()}
    manager.use_button = Button()
    manager.rename_button = Button()
    manager.copy_button = Button()
    manager.delete_button = Button()
    manager.summary = SimpleNamespace(setPlainText=lambda text: setattr(manager, "summary_text", text))
    manager.dialog = Dialog()
    manager.accepted = False
    manager.selected = None
    manager._qt = SimpleNamespace(
        QMessageBox=SimpleNamespace(
            Yes=1,
            question=lambda *_args: answer,
            warning=lambda _parent, _title, message: setattr(manager, "warning", message),
        ),
        QInputDialog=SimpleNamespace(getText=lambda *_args, **_kwargs: input_name),
    )
    return manager


def test_use_changes_only_selected_profile_and_does_not_write_it(tmp_path):
    store = ProfileStore(tmp_path)
    profile = Profile(id="profile-a", name="A", conversion="s2twp_jieba",
                      segmentation="jieba", ruleset_ids=("default",))
    path = store.save(profile)
    before = path.stat().st_mtime_ns
    manager = _manager((profile,), store, active=profile, current=profile)
    manager.rules_checks["default"].setChecked(True)
    manager.rules_checks["mine"].setChecked(True)

    manager._use()

    assert manager.accepted
    assert manager.selected.conversion == "s2twp_jieba"
    assert manager.selected.segmentation == "jieba"
    assert manager.selected.ruleset_ids == ("default", "mine")
    assert path.stat().st_mtime_ns == before


def test_delete_removes_profile_and_clears_preference_callback(tmp_path):
    store = ProfileStore(tmp_path)
    profile = Profile(id="profile-a", name="A")
    path = store.save(profile)
    prefs = {"profile_id": profile.id, "ui": {"language": "en"}}

    def clear_deleted(identifier):
        if prefs.get("profile_id") == identifier:
            prefs.pop("profile_id")

    manager = _manager((profile,), store, active=profile, current=profile,
                       answer=1, on_delete=clear_deleted)
    manager._refresh = lambda: None

    manager._delete()

    assert not path.exists()
    assert "profile_id" not in prefs


def test_duplicate_profile_name_is_rejected(tmp_path):
    first = Profile(id="a", name="First")
    second = Profile(id="b", name="Taken")
    manager = _manager((first, second), ProfileStore(tmp_path), input_name=("Taken", True))

    result = manager._ask_name("Profile name", "First")

    assert result is None
    assert manager.warning == "duplicate"


def test_modified_current_profile_cannot_be_deleted(tmp_path):
    store = ProfileStore(tmp_path)
    active = Profile(id="profile-a", name="A", conversion="s2t")
    current = Profile(id="profile-a", name="A", conversion="s2tw")
    store.save(active)
    manager = _manager((active,), store, active=active, current=current, answer=1)
    manager._refresh = lambda: None

    assert not manager._can_delete(active)
    manager._delete()
    assert store._path(active.id).exists()
    assert manager.warning == "modified"


def test_profile_summary_marks_unavailable_jieba_without_rewriting_it(tmp_path):
    profile = Profile(id="jieba", name="Jieba", conversion="s2twp_jieba",
                      segmentation="jieba")
    manager = _manager((profile,), ProfileStore(tmp_path))
    manager._available_config_ids = {"s2twp"}
    manager._refresh_summary()

    assert "s2twp_jieba (unavailable)" in manager.summary_text
    assert manager._current().conversion == "s2twp_jieba"
