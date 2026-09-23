import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)
import tempfile
from pathlib import Path
from types import SimpleNamespace
import fakeqt
from app.settings import RunSettings, profile_options
from app.profiles import Profile
from ui.preview_window import _ConversionConfigDialog
from ui.i18n import Translator
from opencc_backend.configs import V1_CONFIGS

root = Path(tempfile.mkdtemp())
storage = SimpleNamespace(
    paths=SimpleNamespace(root=root, profiles=root / "profiles", rules=root / "rules")
)
settings = RunSettings(storage, SimpleNamespace(), {}, language="en", session_id="s")
for start_config, target in (
    (
        "s2tw",
        Profile(
            id="fp", name="FP", conversion="s2tw", force_pivot=True, pivot_chain=("t2s", "s2tw")
        ),
    ),
    (
        "tw2t",
        Profile(
            id="fp", name="FP", conversion="s2tw", force_pivot=True, pivot_chain=("t2s", "s2tw")
        ),
    ),
    (
        "s2t",
        Profile(
            id="fp2", name="FP2", conversion="t2s", force_pivot=True, pivot_chain=("s2tw", "t2s")
        ),
    ),
):
    settings.active = Profile(id="conservative", name="Conservative", conversion=start_config)
    settings.pick_profile = lambda config, options, tr, _t=target: _t
    qt = fakeqt.make()
    d = _ConversionConfigDialog(
        qt,
        tuple(V1_CONFIGS),
        start_config,
        {},
        translator=Translator("en"),
        initial_options=profile_options(settings.active),
        services=settings,
    )
    d.options_panel._tool("profiles")
    v = d.options_panel.values()
    print(
        f"start={start_config} load {target.conversion} force_pivot={target.force_pivot} chain={target.pivot_chain} -> "
        f"direction={d.combo.currentData()} force_pivot={v['force_pivot']} chain={v['pivot_chain']}"
    )
print("slot exceptions:", [repr(e) for e in fakeqt.LOG if isinstance(e, Exception)][:3])
