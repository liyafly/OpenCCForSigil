from types import SimpleNamespace

from app.profiles import Profile, ProfileStore
from opencc_backend.configs import SUPPORTED_CONFIGS, V1_CONFIGS
from ui.profile_window import ProfileManagerDialog


class Signal:
    def connect(self, _callback):
        return None


class Combo:
    def __init__(self, items=()):
        self.items = list(items)
        self.index = 0 if self.items else -1
        self.currentIndexChanged = Signal()

    def addItem(self, text, data):
        self.items.append((text, data))
        if self.index < 0:
            self.index = 0

    def findData(self, data):
        return next((index for index, item in enumerate(self.items) if item[1] == data), -1)

    def setCurrentIndex(self, index):
        self.index = index

    def currentIndex(self):
        return self.index

    def currentData(self):
        return self.items[self.index][1] if 0 <= self.index < len(self.items) else None


class Edit:
    def __init__(self, value=""):
        self.value = value

    def setText(self, value):
        self.value = value

    def text(self):
        return self.value


class Check:
    def __init__(self):
        self.checked = False
        self.enabled = True
        self.tooltip = ""

    def setChecked(self, value):
        self.checked = value

    def isChecked(self):
        return self.checked

    def setEnabled(self, value):
        self.enabled = value

    def setToolTip(self, value):
        self.tooltip = value


class Dialog:
    def __init__(self):
        self.accepted = False

    def accept(self):
        self.accepted = True


def _manager(profile, available_configs, store):
    manager = object.__new__(ProfileManagerDialog)
    manager._profiles = [profile]
    manager._available_configs = V1_CONFIGS
    manager._available_config_ids = set(available_configs)
    manager._jieba_configs = {
        base: config for base, config in {
            "s2t": "s2t_jieba", "s2tw": "s2tw_jieba", "s2twp": "s2twp_jieba",
            "s2hk": "s2hk_jieba", "s2hkp": "s2hkp_jieba", "tw2sp": "tw2sp_jieba",
            "hk2sp": "hk2sp_jieba",
        }.items() if config in manager._available_config_ids
    }
    manager._labels = {"title": "Profiles", "unavailable": "unavailable on this host"}
    manager._loading = False
    manager.combo = Combo(((profile.name, profile.id),))
    manager.name_edit = Edit()
    manager.config_combo = Combo((config, config) for config in V1_CONFIGS)
    manager.jieba_checkbox = Check()
    manager.rules_edit = Edit()
    manager._store = store
    manager._qt = SimpleNamespace(QMessageBox=SimpleNamespace(warning=lambda *_args: None))
    manager.dialog = Dialog()
    manager.accepted = False
    manager.selected = None
    return manager


def test_renaming_jieba_profile_preserves_config_and_derives_segmentation(tmp_path):
    store = ProfileStore(tmp_path)
    profile = Profile(id="jieba-profile", name="Old name", conversion="s2twp_jieba",
                      segmentation="jieba")
    manager = _manager(profile, SUPPORTED_CONFIGS, store)
    manager._load()
    manager.name_edit.setText("Renamed")

    manager._save()

    saved = store.load(profile.id)
    assert saved.name == "Renamed"
    assert saved.conversion == "s2twp_jieba"
    assert saved.segmentation == "jieba"


def test_unavailable_jieba_profile_is_visible_and_kept_on_save(tmp_path):
    store = ProfileStore(tmp_path)
    profile = Profile(id="jieba-profile", name="Jieba", conversion="s2twp_jieba",
                      segmentation="jieba")
    manager = _manager(profile, V1_CONFIGS, store)
    manager._load()

    assert manager.config_combo.currentData() == "s2twp_jieba"
    assert "unavailable" in manager.config_combo.items[manager.config_combo.currentIndex()][0]
    assert not manager.jieba_checkbox.enabled
    manager.name_edit.setText("Jieba renamed")
    manager._save()

    saved = store.load(profile.id)
    assert saved.conversion == "s2twp_jieba"
    assert saved.segmentation == "jieba"


def test_switching_profile_to_standard_config_saves_mmseg(tmp_path):
    store = ProfileStore(tmp_path)
    profile = Profile(id="jieba-profile", name="Jieba", conversion="s2twp_jieba",
                      segmentation="jieba")
    manager = _manager(profile, SUPPORTED_CONFIGS, store)
    manager._load()
    index = manager.config_combo.findData("s2t")
    manager.config_combo.setCurrentIndex(index)
    manager.jieba_checkbox.setChecked(False)
    manager.name_edit.setText("Standard")

    manager._save()

    saved = store.load(profile.id)
    assert saved.conversion == "s2t"
    assert saved.segmentation == "mmseg"
