# ruff: noqa: E402,E702
"""RULE-10/11: probe the rule manager defaults, as RunSettings.edit_rules() opens it.

Uses the repository's fake Qt (tests/support/fake_qt.py); pass --real-qt to use PySide6:
QT_QPA_PLATFORM=offscreen mise exec -- uv run --with PySide6==6.11.2 python <this file> --real-qt
"""
import os
import sys
from pathlib import Path
REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))
sys.path.insert(0, str(REPO))

from rules.store import RuleSet
from ui.i18n import Translator
from ui.rules_window import RuleManagerDialog

if "--real-qt" in sys.argv:
    from ui.qt import ensure_application, load_qt
    qt = load_qt()
    app = ensure_application(qt)
else:
    from tests.support.fake_qt import make_with_table
    qt = make_with_table()

# edit_rules(): values.setdefault("default", RuleSet("default")) when no default.json exists.
window = RuleManagerDialog(
    qt, (), translator=Translator("zh-Hans"), official_convert=lambda _c, v: v,
    config="s2t", profile_id="P", book_fingerprint="B",
    available_configs=("s2t", "t2s", "s2tw", "s2twp"),
    run_options={"ruleset_ids": ("default",)},
    rulesets=(RuleSet("default"),), ruleset_id="default",
)
print("RULE-10 run config = s2t; new-rule direction preselected:", window.direction_combo.currentData(),
      "->", window.direction_combo.currentText())
window.source_edit.setText("里")
window.target_edit.setText("裡")
window._add()
added = window.rules[-1]
print("  added rule:", added.source, "->", added.target, "direction =", repr(added.direction),
      "semantic_version =", added.semantic_version)
from rules.precedence import applies_to
print("  applies to a later t2s run:", applies_to(added, config="t2s"),
      "| applies to s2twp run:", applies_to(added, config="s2twp"))

# Same dialog but a user-created ruleset: _new_ruleset() uses base_direction(config)
w2 = RuleManagerDialog(
    qt, (), translator=Translator("zh-Hans"), official_convert=lambda _c, v: v,
    config="s2t", available_configs=("s2t", "t2s"),
    rulesets=(RuleSet("mine", default_direction="s2t"),), ruleset_id="mine",
    run_options={"ruleset_ids": ("mine",)},
)
w2.source_edit.setText("软件"); w2.target_edit.setText("軟體"); w2._add()
r = w2.rules[-1]
print("  for comparison, rule in a user-created set: direction =", repr(r.direction),
      "| applies to s2twp run:", applies_to(r, config="s2twp"))

print("\nRULE-11 label of ruleset-level switch:", window.ruleset_enabled_check.text())

# What the '*' default does to a later t2s book (real vendored OpenCC):
from opencc_backend.backend import OpenCCBackend
from core.converter import OfficialBackendConverter
from core.models import ConvertRequest, RuleSnapshot as RequestRuleSnapshot
from rules.models import RuleSnapshot
backend = OpenCCBackend("t2s")
try:
    text = "他每天走三公里去鄰里的學校。"
    plain = backend.convert(text)
    snapshot = RuleSnapshot.freeze((added,))
    request = ConvertRequest(
        "t2s",
        rules_snapshot=RequestRuleSnapshot(rules_hash=snapshot.sha256, rules=snapshot.rules),
        detailed_classification=False,
        diagnose_mixed=False,
    )
    ruled = OfficialBackendConverter(backend).convert(text, request).target
    print("  t2s without rule:", plain)
    print("  t2s with the '*' rule added during an s2t session:", ruled)
finally:
    backend.close()
