# ruff: noqa: E402
"""FIX-14: verify deleting a ruleset also prunes persisted run options.

Run from the repository root. Uses a temporary data directory, never user data.
"""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))
sys.path.insert(0, str(REPO))

from app.settings import RunSettings
from rules.store import RuleSet, RuleStore
from sigil.storage import UserDataStore
from tests.support.fake_qt import make_with_table
from ui import rules_window
from ui.i18n import Translator
from ui.rules_window import RuleWindowResult


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    storage = UserDataStore(root)
    storage.update_preferences({"run_options": {"ruleset_ids": ["default", "X"]}})
    RuleStore(storage.paths.rules).save(RuleSet("X"))
    settings = RunSettings(
        storage,
        SimpleNamespace(book_fingerprint=lambda: "B"),
        storage.load_preferences(),
        language="en",
        session_id="1",
    )
    print("session 1 active:", settings.active.ruleset_ids,
          "| profile saved:", settings.active_profile_is_saved)
    rules_window.show_rules_window = lambda *args, **kwargs: RuleWindowResult(
        "default",
        (RuleSet("default"),),
        run_ruleset_ids=("default",),
        deleted=("X",),
    )
    settings.edit_rules("s2t", Translator("en"), make_with_table(), None)
    print("after delete: active:", settings.active.ruleset_ids,
          "| X.json exists:", (storage.paths.rules / "X.json").exists())

    next_settings = RunSettings(
        storage,
        SimpleNamespace(book_fingerprint=lambda: "B"),
        storage.load_preferences(),
        language="en",
        session_id="2",
    )
    print("next launch: missing-ruleset notice =", next_settings.take_missing_rulesets_notice())
