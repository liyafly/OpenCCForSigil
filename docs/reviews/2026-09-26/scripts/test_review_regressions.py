"""Desired-behavior reproductions for the 2026-09-26 review.

These intentionally fail on e5329e7. They are outside the normal testpaths.
Run from the repository root with:
  mise exec -- uv run python -m pytest docs/reviews/2026-09-26/scripts/test_review_regressions.py -q
"""

from dataclasses import replace
from io import StringIO
import json
from types import SimpleNamespace

import pytest

from app.settings import RunSettings
from core.converter import OfficialBackendConverter
from core.models import ConvertRequest, RuleSnapshot as RequestSnapshot
from core.planner import build_conversion_plan
from core.preview import PreviewSession
from document.tokenizer import tokenize_xhtml
from rules.exporters import export_rules, export_warnings
from rules.importers import import_rules
from rules.matching import RuleExecutionError
from rules.models import Rule, RuleSnapshot
from rules.store import RuleSet, RuleStore
from tests.support.fake_qt import make_with_table
from ui.i18n import Translator
from ui.preview_window import _PreviewDialog
from ui.rules_window import RuleManagerDialog, RuleWindowResult


class IdentityBackend:
    config = "s2t"

    def convert(self, text):
        return text

    def convert_for_config(self, _config, text):
        return text

    def provenance(self):
        return SimpleNamespace(as_dict=lambda: {"review_backend": "identity"})


def replacement(**values):
    return Rule.from_dict({
        "id": "r", "source": "旧词", "target": "新词", "direction": "s2t",
        "semantic_version": 2, "action": "replace", "stage": "pre",
        "match_type": "literal", **values,
    })


def request(rules):
    snapshot = RuleSnapshot.freeze(rules)
    return ConvertRequest(
        "s2t", rules_snapshot=RequestSnapshot(
            rules_hash=snapshot.rules_hash, rules=snapshot.rules),
        detailed_classification=False, diagnose_mixed=False,
    )


def manager(rules=(), **kwargs):
    return RuleManagerDialog(
        make_with_table(), tuple(rules), translator=Translator("en"),
        official_convert=IdentityBackend(), **kwargs,
    )


def test_r01_clearing_default_ruleset_is_persisted(tmp_path, monkeypatch):
    store = RuleStore(tmp_path / "rules")
    store.save(RuleSet("default", (replacement(),)))
    storage = SimpleNamespace(paths=SimpleNamespace(
        root=tmp_path, rules=tmp_path / "rules", profiles=tmp_path / "profiles"))
    settings = RunSettings(
        storage, SimpleNamespace(book_fingerprint=lambda: "book"),
        {"run_options": {"ruleset_ids": ["default"]}},
        language="en", session_id="review",
    )
    monkeypatch.setattr("ui.rules_window.show_rules_window", lambda *a, **kw:
                        RuleWindowResult("default", (RuleSet("default"),)))
    settings.edit_rules("s2t", Translator("en"), make_with_table(), None)
    assert store.load("default").rules == ()
    assert settings.freeze_rules(settings.active).rules == ()


def test_r02_edit_preserves_owner_version_and_annotations():
    original = Rule(
        id="owned", source="旧词", target="旧目标", direction="s2t", scope="book",
        book_fingerprint="book-A", semantic_version=1,
        comment="Keep this comment", source_note="Keep this source",
    )
    window = manager((original,), book_fingerprint="book-B", profile_id="profile-B")
    window.table.selectRow(0)
    window._load_selected()
    window.target_edit.setText("新目标")
    window._update_selected()
    actual = window.rules[0]
    assert (actual.book_fingerprint, actual.semantic_version, actual.comment, actual.source_note) == (
        "book-A", 1, "Keep this comment", "Keep this source")


@pytest.mark.parametrize("delta", [
    {"stage": "post"}, {"match_type": "regex"}, {"enabled": False},
    {"action": "override", "stage": "source"},
])
def test_r03_import_preserves_distinct_rule_semantics(delta):
    first = replacement(id="first")
    second = replace(first, id="second", **delta)
    result = import_rules(StringIO(export_rules((first, second))), format="json")
    assert len(result.rules) == 2
    assert result.duplicates == ()


@pytest.mark.parametrize("format", ["csv", "tsv", "txt"])
def test_r04_export_warns_before_dropping_regex_stage_and_scope(format):
    rule = replacement(match_type="regex", source="旧.+", scope="book", book_fingerprint="A")
    lossy, _skipped = export_warnings((rule,), format=format)
    assert lossy is True


def test_r05_independent_rule_occurrences_have_independent_decisions():
    rule = replacement(source="a123b", target="x123y")
    plans = []
    for file_id in ("chapter-A", "chapter-B"):
        source = "<html><body><p>a123b</p><p>a123b</p></body></html>"
        plans.append(build_conversion_plan(
            file_id=file_id, source=source, document=tokenize_xhtml(source),
            backend=IdentityBackend(), request=request((rule,)),
        ))
    previews = [PreviewSession(plan) for plan in plans]
    entries = [(preview, change) for preview in previews for change in preview.changes]
    first_group = entries[0][1].group_id
    assert first_group
    # Exercise the same group mutation used by the UI's Accept this action.
    shell = object.__new__(_PreviewDialog)
    shell._entries = entries
    changed = shell._decide_group(first_group, True)
    assert changed == 2  # two patches in one occurrence, not eight across four occurrences
    assert previews[0].summary()["accepted"] == 2
    assert previews[1].summary()["accepted"] == 0


def test_r06_disabled_ruleset_is_not_applied_in_run_sandbox():
    rule = replacement()
    window = manager((rule,), rulesets=(RuleSet("off", (rule,), enabled=False),), ruleset_id="off")
    window.test_input.setPlainText("旧词")
    window._test()
    final_line = Translator("en").text("rules.final_label") + ": 旧词"
    assert final_line in window.test_output.toPlainText().splitlines()


def test_r07_sandbox_counts_one_final_wording_hit_once():
    rule = Rule(id="final", source="旧词", target="新词", direction="s2t")
    window = manager((rule,))
    window.test_input.setPlainText("旧词")
    window._test()
    hit_line = Translator("en").text("rules.hits_label") + ": 1"
    assert hit_line in window.test_output.toPlainText().splitlines()


def test_r08_unsubmitted_editor_draft_is_guarded(monkeypatch):
    window = manager()
    window.source_edit.setText("未添加的草稿")
    window.target_edit.setText("新词")
    confirmations = []

    def stay():
        confirmations.append(True)
        return False

    monkeypatch.setattr(window, "_confirm_discard_rules", stay)
    assert window._guard_reject() is False
    assert confirmations == [True]


def test_r09_empty_replacement_is_displayed_as_deletion():
    rule = replacement(target="")
    window = manager((rule,))
    # Blank or a dedicated localized deletion label is valid; echoing the source is not.
    assert window.table.item(0, 3).text() != rule.source


def test_r10_regex_final_wording_obeys_output_budget(monkeypatch):
    monkeypatch.setattr("rules.matching.REGEX_MAX_OUTPUT_CHARS_PER_RUN", 4)
    rule = replacement(
        action="override", stage="source", match_type="regex", source="x", target="12345")
    with pytest.raises(RuleExecutionError, match="output"):
        OfficialBackendConverter(IdentityBackend()).convert("x", request((rule,)))


def test_r12_lenient_json_import_keeps_valid_records_and_reports_bad_record():
    payload = [
        replacement(id="first").to_dict(),
        {**replacement(id="bad").to_dict(), "unknown_field": True},
        replacement(id="last", source="末尾", target="尾部").to_dict(),
    ]
    result = import_rules(StringIO(json.dumps(payload)), format="json", strict=False)
    assert [rule.id for rule in result.rules] == ["first", "last"]
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].severity == "error"
