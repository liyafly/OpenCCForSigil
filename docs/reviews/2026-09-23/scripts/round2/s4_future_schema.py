"""S4: profile/ruleset files written by a newer plugin version are renamed to *.corrupt-*."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)
import tempfile
import json
from pathlib import Path
from types import SimpleNamespace

from sigil.storage import UserDataStore
from app.settings import RunSettings
from app.profiles import Profile

with tempfile.TemporaryDirectory() as d:
    storage = UserDataStore(Path(d))
    storage.ensure_layout()
    p = Profile(id="mine", name="Mine", ruleset_ids=("newer",)).to_dict()
    p["schema_version"] = 2
    (storage.paths.profiles / "mine.json").write_text(json.dumps(p), encoding="utf-8")
    (storage.paths.rules / "newer.json").write_text(
        json.dumps({"schema_version": 2, "id": "newer", "rules": []}), encoding="utf-8"
    )
    s = RunSettings(
        storage,
        SimpleNamespace(),
        {"profile_id": "mine", "run_options": {"ruleset_ids": ["newer"]}},
        language="en",
        session_id="x",
    )
    print(
        "active:",
        s.active.id,
        "notice:",
        s.recovery_notice,
        "clear pref:",
        s.clear_profile_preference,
    )
    print("profiles dir:", sorted(x.name for x in storage.paths.profiles.iterdir()))
    print("rules dir:", sorted(x.name for x in storage.paths.rules.iterdir()))
    print("missing notice:", s.take_missing_rulesets_notice())
