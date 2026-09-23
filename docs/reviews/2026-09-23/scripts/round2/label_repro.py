import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)
import tempfile
from pathlib import Path
from types import SimpleNamespace
import fakeqt
from app.settings import RunSettings, profile_options
from app.profiles import Profile, ProfileStore
from ui.run_options import RunOptionsPanel
from ui.i18n import Translator

root = Path(tempfile.mkdtemp())
storage = SimpleNamespace(
    paths=SimpleNamespace(root=root, profiles=root / "profiles", rules=root / "rules")
)
ProfileStore(root / "profiles").save(Profile(id="p1", name="Mine", conversion="s2t"))
settings = RunSettings(
    storage, SimpleNamespace(), {"profile_id": "p1"}, language="zh-Hans", session_id="s"
)
print("saved profile convert_nav:", settings.active.convert_nav)
for nav_available in (True, False):
    qt = fakeqt.make()
    layout = qt.QVBoxLayout()
    panel = RunOptionsPanel(
        qt,
        Translator("zh-Hans"),
        layout,
        initial=profile_options(settings.active),
        metadata_available=True,
        nav_available=nav_available,
        services=settings,
    )
    panel.bind(lambda: "s2t", lambda c: None, None)
    print(
        f"nav_available={nav_available}: label={panel.profile_label.text()!r} include_nav={panel.values()['include_nav']}"
    )
cur = settings.current_profile("s2t", panel.values()).to_dict()
act = settings.active.to_dict()
print(
    "differing keys:",
    {k: (act.get(k), cur.get(k)) for k in set(act) | set(cur) if act.get(k) != cur.get(k)},
)
# default (unsaved) conservative profile too
settings2 = RunSettings(storage, SimpleNamespace(), {}, language="en", session_id="s")
qt = fakeqt.make()
layout = qt.QVBoxLayout()
p2 = RunOptionsPanel(
    qt,
    Translator("en"),
    layout,
    initial=profile_options(settings2.active),
    nav_available=True,
    services=settings2,
)
p2.bind(lambda: settings2.active.conversion, lambda c: None, None)
print("conservative default:", p2.profile_label.text())
cur = settings2.current_profile(settings2.active.conversion, p2.values()).to_dict()
act = settings2.active.to_dict()
print(
    "differing keys:",
    {k: (act.get(k), cur.get(k)) for k in set(act) | set(cur) if act.get(k) != cur.get(k)},
)
from ui.profile_window import ProfileManagerDialog

qt = fakeqt.make()
layout = qt.QVBoxLayout()
p3 = RunOptionsPanel(
    qt,
    Translator("en"),
    layout,
    initial=profile_options(settings.active),
    nav_available=True,
    services=settings,
)
p3.bind(lambda: "s2t", lambda c: None, None)
draft = settings.current_profile("s2t", p3.values())
qt = fakeqt.make()
qt.QInputDialog = None
m = ProfileManagerDialog(
    qt,
    (draft,),
    translator=Translator("en"),
    store=settings.profiles,
    selected_id=draft.id,
    current_profile=draft,
    active_profile=settings.active,
)
print(
    "untouched saved active profile -> rename enabled:",
    m.rename_button.isEnabled(),
    "delete enabled:",
    m.delete_button.isEnabled(),
)
