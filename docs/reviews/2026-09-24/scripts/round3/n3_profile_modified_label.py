"""N-03 (R-19 leftover): an untouched profile shows "(modified)" and cannot be renamed.

Expect after the fix: label without "(modified)", rename/delete enabled, diff == {}.
"""

import tempfile
from pathlib import Path
from types import SimpleNamespace

import common  # noqa: F401
import ui.profile_window as profile_window
from app.profiles import Profile, ProfileStore
from app.settings import RunSettings, profile_options
from sigil.storage import UserDataStore
from tests.support import fake_qt
from ui.i18n import Translator
from ui.profile_window import ProfileManagerDialog, _profile_signature
from ui.run_options import RunOptionsPanel

storage = UserDataStore(Path(tempfile.mkdtemp()))
storage.ensure_layout()
ProfileStore(storage.paths.profiles).save(Profile(id="p1", name="Mine", conversion="s2t"))
settings = RunSettings(storage, SimpleNamespace(), {"profile_id": "p1"}, language="en",
                       session_id="s")
qt = fake_qt.make()
panel = RunOptionsPanel(qt, Translator("en"), qt.QVBoxLayout(),
                        initial=profile_options(settings.active), metadata_available=True,
                        nav_available=True, services=settings)
panel.bind(lambda: "s2t", lambda _config: None, None)
print("label:", panel.profile_label.text())

captured = {}


def fake_show(values, **kwargs):
    captured.update(kwargs)
    captured["manager"] = ProfileManagerDialog(fake_qt.make(), values, **kwargs)


profile_window.show_profile_window = fake_show
settings.pick_profile("s2t", panel.values(), Translator("en"))
manager = captured["manager"]
print("rename enabled:", manager.rename_button.isEnabled(),
      "delete enabled:", manager.delete_button.isEnabled())
active = dict(_profile_signature(captured["active_profile"]))
current = dict(_profile_signature(captured["current_profile"]))
print("diff:", {key: (active.get(key), current.get(key))
                for key in set(active) | set(current) if active.get(key) != current.get(key)})
