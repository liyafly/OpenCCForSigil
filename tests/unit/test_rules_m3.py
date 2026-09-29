from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from core.converter import OfficialBackendConverter
from core.models import ConvertRequest, RuleSnapshot as RequestRuleSnapshot
from core.staging import apply_changes
from rules.conflicts import (
    BlockingRuleConflict,
    blocking_conflicts,
    find_conflicts,
    validate_no_blocking_conflicts,
)
from rules.compiled import CompiledOverlay, lock_spans_compiled
from rules.exporters import export_rules, export_warnings
from rules.importers import import_rules, reassign_colliding_ids
from rules.models import Rule, RuleSnapshot
from rules.store import RuleSet, RuleStore


class _Backend:
    def __init__(self, official):
        self.official = official
        self.calls = []

    def convert(self, text):
        self.calls.append(text)
        return self.official(text)

    def convert_for_config(self, _config, text):
        return self.convert(text)

    def provenance(self):
        return SimpleNamespace(as_dict=lambda: {"backend": "test"})


def _request(snapshot, *, config="s2t", profile_id="", book_fingerprint=""):
    return ConvertRequest(
        config,
        rules_snapshot=RequestRuleSnapshot(
            rules_hash=snapshot.sha256,
            rules=snapshot.rules,
        ),
        profile_id=profile_id,
        book_fingerprint=book_fingerprint,
        detailed_classification=False,
        diagnose_mixed=False,
        include_rule_trace=True,
    )


def _convert(text, official, snapshot, **options):
    config = options.pop("config", "s2t")
    return OfficialBackendConverter(_Backend(official)).convert(
        text, _request(snapshot, config=config, **options))


def _locked(text, snapshot, *, config, profile_id=None, book_fingerprint=None):
    overlay = CompiledOverlay.build(
        snapshot,
        config=config,
        profile_id=profile_id,
        book_fingerprint=book_fingerprint,
    )
    return lock_spans_compiled(text, overlay)


def test_locked_targets_are_never_reconverted_and_longest_match_wins():
    calls = []

    def official(text: str) -> str:
        calls.append(text)
        return text.replace("这", "這").replace("這", "這").replace("着", "著").replace("台", "臺")

    snapshot = RuleSnapshot.freeze(
        [
            Rule(direction="s2twp", source="服务器", target="服務器"),
            Rule(direction="s2twp", type="protect", source="着", target="着"),
            Rule(direction="s2twp", source="服", target="服字"),
        ]
    )
    result = _convert("这台服务器着火了", official, snapshot, config="s2twp")
    assert result.target == "這臺服務器着火了"
    assert "服务器" not in "".join(calls)
    assert next(trace for trace in result.rule_trace if trace.action == "protect").source == "着"


def test_direction_scope_and_disabled_rules():
    snapshot = RuleSnapshot.freeze(
        [
            Rule(direction="t2s", source="服务器", target="X"),
            Rule(direction="s2t", source="软件", target="Y", enabled=False),
            Rule(direction="s2t", source="软件", target="Z", scope="profile", profile_id="p"),
        ]
    )
    assert _locked("软件", snapshot, config="s2t", profile_id="other") == ()
    assert _locked("软件", snapshot, config="s2t", profile_id="p")[0].target == "Z"


def test_v1_book_rule_beats_v2_global_rule_at_same_position():
    rules = (
        Rule(id="v1-book", direction="s2t", source="头发", target="頭髮(书)",
             scope="book", book_fingerprint="B", semantic_version=1),
        Rule(id="v2-global", direction="s2t", source="头发", target="頭髮(全局)",
             scope="global", semantic_version=2, action="override", stage="source"),
    )

    result = _convert(
        "头发", lambda value: value, RuleSnapshot.freeze(rules), book_fingerprint="B",
    )

    assert result.target == "頭髮(书)"


def test_cross_version_same_source_different_target_is_blocking():
    rules = (
        Rule(id="v1", direction="s2t", source="软件", target="軟體",
             semantic_version=1),
        Rule(id="v2", direction="s2t", source="软件", target="軟件",
             semantic_version=2, action="override", stage="source"),
    )

    conflicts = blocking_conflicts(rules)

    assert conflicts
    assert conflicts[0].kind == "SAME_SOURCE_DIFFERENT_TARGET"


def test_all_standard_directions_and_jieba_base_direction():
    directions = (
        "s2t",
        "t2s",
        "s2tw",
        "tw2s",
        "s2twp",
        "tw2sp",
        "s2hk",
        "hk2s",
        "s2hkp",
        "hk2sp",
        "t2tw",
        "tw2t",
        "t2hk",
        "hk2t",
        "t2jp",
        "jp2t",
    )
    for direction in directions:
        snapshot = RuleSnapshot.freeze([Rule(direction=direction, source="词", target="詞")])
        assert _locked("词", snapshot, config=direction)[0].target == "詞"
    snapshot = RuleSnapshot.freeze([Rule(direction="s2t", source="词", target="詞")])
    assert _locked("词", snapshot, config="s2t_jieba")[0].target == "詞"


def test_profile_and_book_selectors_do_not_cross_conflict():
    rules = (
        Rule(
            direction="*", source="词", target="甲", scope="profile", profile_id="one", priority=1
        ),
        Rule(
            direction="s2t", source="词", target="乙", scope="profile", profile_id="two", priority=1
        ),
        Rule(
            direction="*",
            source="书",
            target="甲",
            scope="book",
            book_fingerprint="one",
            priority=1,
        ),
        Rule(
            direction="s2t",
            source="书",
            target="乙",
            scope="book",
            book_fingerprint="two",
            priority=1,
        ),
    )
    assert find_conflicts(rules) == ()


def test_conflict_blocks_before_official_callback():
    snapshot = RuleSnapshot.freeze(
        [
            Rule(direction="s2t", source="服务器", target="伺服器", priority=10),
            Rule(direction="s2t", source="服务器", target="服務器", priority=10),
        ]
    )
    assert blocking_conflicts(snapshot.rules)
    with pytest.raises(BlockingRuleConflict):
        _convert("服务器", lambda value: value, snapshot)


def test_import_export_round_trip_and_opencc_diagnostic():
    source = "# comment\n服务器\t伺服器 服務器\n"
    imported = import_rules(source, format="opencc-txt", direction="s2t")
    assert imported.rules[0].target == "伺服器"
    assert "discarded" in imported.diagnostics[0].message
    payload = export_rules(imported.rules, format="json")
    assert json.loads(payload)["schema_version"] == 1
    round_trip = import_rules(payload, format="json")
    assert round_trip.rules[0].source == "服务器"


def test_regex_is_explicitly_unsupported_and_snapshot_is_immutable():
    imported = import_rules(
        json.dumps(
            {"rules": [{"type": "regex", "direction": "s2t", "source": "x", "target": "y"}]}
        )
    )
    assert imported.rules == ()
    assert len(imported.diagnostics) == 1
    assert "V1.1" in imported.diagnostics[0].message
    original = RuleSnapshot.freeze([Rule(direction="s2t", source="a", target="b")])
    mutated = Rule(direction="s2t", source="a", target="c")
    assert original.rules[0].target == "b"
    assert original.sha256 != RuleSnapshot.freeze([mutated]).sha256


def test_segment_changes_reconstruct_exact_final_with_adjacent_length_changes():
    snapshot = RuleSnapshot.freeze([Rule(direction="s2t", source="术语", target="術語")])

    def official(value: str) -> str:
        return value.replace("一", "壹").replace("二", "貳")

    source = "一术语二"
    result = _convert(source, official, snapshot)
    assert result.target == "壹術語貳"
    assert apply_changes(source, result.changes) == result.target


def test_non_string_backend_output_is_rejected():
    snapshot = RuleSnapshot.freeze(())
    with pytest.raises(TypeError):
        _convert("软件", lambda value: None, snapshot)


def test_repeated_protected_text_keeps_each_locked_boundary():
    snapshot = RuleSnapshot.freeze(
        [Rule(type="protect", direction="s2t", source="甲", target="甲")]
    )
    source = "甲乙甲乙甲"
    result = _convert(source, lambda value: value.replace("乙", "乙字"), snapshot)
    assert result.target == "甲乙字甲乙字甲"
    assert sum(trace.action == "protect" for trace in result.rule_trace) == 3
    assert apply_changes(source, result.changes) == result.target


def test_snapshot_from_dict_checks_supplied_hash_and_requires_direction():
    snapshot = RuleSnapshot.freeze([Rule(direction="s2t", source="a", target="b")])
    payload = snapshot.to_dict()
    assert RuleSnapshot.from_dict(payload).sha256 == snapshot.sha256
    payload["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="sha256"):
        RuleSnapshot.from_dict(payload)
    imported = import_rules('{"rules":[{"source":"a","target":"b"}]}')
    assert imported.rules == ()
    assert len(imported.diagnostics) == 1
    assert "direction" in imported.diagnostics[0].message


def test_ruleset_schema_two_applies_defaults_and_preserves_enabled_state():
    ruleset = RuleSet.from_dict({
        "schema_version": 2,
        "id": "configured",
        "semantic_version": 2,
        "default_direction": "s2t",
        "default_scope": "global",
        "enabled": False,
        "rules": [{"id": "space", "source": " ", "target": ""}],
    })

    assert ruleset.semantic_version == 2
    assert ruleset.default_direction == "s2t"
    assert ruleset.default_scope == "global"
    assert not ruleset.enabled
    assert ruleset.rules[0].semantic_version == 2
    assert ruleset.rules[0].action == "override"
    assert ruleset.rules[0].direction == "s2t"
    assert ruleset.rules[0].source == " "


def test_legacy_ruleset_migration_keeps_v1_semantics_and_backs_up_source(tmp_path):
    store = RuleStore(tmp_path)
    original = {
        "schema_version": 1,
        "id": "legacy",
        "rules": [{
            "id": "old-rule", "type": "exact", "direction": "s2t",
            "source": "旧词", "target": "舊詞",
        }],
    }
    path = store.directory / "legacy.json"
    path.parent.mkdir(parents=True)
    original_bytes = (json.dumps(original, ensure_ascii=False) + "\n").encode()
    path.write_bytes(original_bytes)

    migrated = store.load("legacy")
    store.save(migrated)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["schema_version"] == 2
    assert saved["semantic_version"] == 1
    assert saved["rules"][0]["semantic_version"] == 1
    assert store.load("legacy").rules[0].action == "override"
    assert path.with_suffix(".json.v1.bak").read_bytes() == original_bytes


def test_v1_and_v2_scope_precedence_both_follow_the_spec():
    def winning_target(rules):
        spans = _locked(
            "术语", RuleSnapshot.freeze(rules), config="s2t", profile_id="profile")
        return spans[0].target

    legacy = (
        Rule(id="global-old", direction="s2t", source="术语", target="全局"),
        Rule(id="profile-old", direction="s2t", source="术语", target="方案",
             scope="profile", profile_id="profile"),
    )
    current = (
        replace(legacy[0], id="global-new", semantic_version=2, action="override"),
        replace(legacy[1], id="profile-new", semantic_version=2, action="override"),
    )

    assert winning_target(legacy) == "全局"
    assert winning_target(current) == "全局"


def test_unrelated_v2_rule_does_not_flip_v1_scope_winner():
    global_rule = Rule(
        id="v1-global", direction="s2t", source="软件", target="軟件(全局)",
        semantic_version=1)
    profile_rule = Rule(
        id="v1-profile", direction="s2t", source="软件", target="軟體(方案)",
        scope="profile", profile_id="profile", semantic_version=1)
    unrelated_v2_rule = Rule(
        id="v2-short", direction="s2t", source="软", target="軟",
        semantic_version=2, action="override", stage="source")

    def winning_id(rules):
        spans = _locked(
            "软件", RuleSnapshot.freeze(rules), config="s2t", profile_id="profile")
        return spans[0].rule.id

    assert winning_id((global_rule, profile_rule)) == "v1-global"
    assert winning_id((global_rule, profile_rule, unrelated_v2_rule)) == "v1-global"


def test_v2_whitespace_source_remains_valid():
    rule = Rule(
        id="whitespace-v2", semantic_version=2, direction="s2t", source=" ", target="")

    overlay = CompiledOverlay.build(RuleSnapshot.freeze((rule,)), config="s2t")

    assert overlay.rules[0].source == " "


def test_global_conflicts_ignore_inactive_profile_owner_fields():
    rules = [
        Rule(id="one", direction="s2t", source="软件", target="甲", scope="global", profile_id="a"),
        Rule(id="two", direction="s2t", source="软件", target="乙", scope="global", profile_id="b"),
    ]
    assert blocking_conflicts(rules)


def test_json_import_reassigns_ids_used_by_another_ruleset(tmp_path):
    store = RuleStore(tmp_path)
    original = Rule(id="shared", direction="s2t", source="头发", target="頭髮")
    store.save(RuleSet("A", (original,)))
    exported = export_rules((original,), format="json")
    store.save(RuleSet("A", (replace(original, enabled=False),)))
    store.save(RuleSet("B"))

    imported = import_rules(exported, format="json")
    saved_rulesets, errors = store.list()
    assert errors == ()
    existing_ids = {rule.id for ruleset in saved_rulesets for rule in ruleset.rules}
    rules = reassign_colliding_ids(imported.rules, existing_ids)
    store.save(RuleSet("B", rules))

    current = store.load("B").rules[0]
    assert current.id != original.id
    assert (current.source, current.target) == (original.source, original.target)
    validate_no_blocking_conflicts(store.load_many(("A", "B")))


def test_json_import_keeps_ids_when_importing_into_empty_store(tmp_path):
    original = Rule(id="kept", direction="s2t", source="头发", target="頭髮")
    imported = import_rules(export_rules((original,), format="json"), format="json")

    assert reassign_colliding_ids(imported.rules, set()) == imported.rules


def test_opencc_txt_export_skips_targets_with_whitespace():
    rules = (
        Rule(direction="s2t", source="Apple", target="Apple Inc"),
        Rule(semantic_version=2, direction="s2t", source="软件", target="軟體"),
    )

    assert export_warnings(rules, format="txt") == (True, 1)
    assert export_rules(rules, format="txt") == "软件\t軟體\n"


def test_opencc_txt_skips_every_unrepresentable_rule():
    rules = (
        Rule(id="plain", semantic_version=2, direction="*", source="term", target="word"),
        Rule(id="regex", semantic_version=2, action="replace", stage="pre",
             match_type="regex", direction="s2t", source="term.+", target="word"),
        Rule(id="protect", direction="s2t", type="protect", source="protected",
             target="protected"),
        Rule(id="disabled", direction="s2t", source="disabled", target="word",
             enabled=False),
        Rule(id="empty", semantic_version=2, action="replace", stage="post",
             direction="s2t", source="empty", target=""),
        Rule(id="whitespace", direction="s2t", source="space", target="two words"),
        Rule(id="tab", direction="s2t", source="tab\tterm", target="word"),
        Rule(id="comment", direction="s2t", source="#comment", target="word"),
    )

    assert export_warnings(rules, format="txt") == (True, 7)
    assert export_rules(rules, format="txt") == "term\tword\n"


def test_delimited_export_reports_lossy_rule_semantics():
    rules = (
        Rule(direction="s2t", source="禁用", target="disabled", enabled=False),
        Rule(direction="s2t", type="protect", source="保护", target="保护"),
        Rule(direction="s2t", source="priority", target="priority", priority=10),
    )

    assert export_warnings(rules, format="tsv") == (True, 0)


def test_delimited_export_does_not_warn_for_v2_version_alone():
    rule = Rule(
        id="v2-exact", semantic_version=2, action="override", stage="source",
        match_type="literal", direction="s2t", source="软件", target="軟體")

    assert export_warnings((rule,), format="tsv") == (False, 0)


def test_delimited_export_reports_all_semantic_fields_it_cannot_preserve():
    v2_regex = Rule(
        id="regex", semantic_version=2, action="replace", match_type="regex",
        stage="post", direction="s2t", source=r"term.+", target="word",
        scope="book", book_fingerprint="book-hash",
    )

    for format in ("csv", "tsv"):
        assert export_warnings((v2_regex,), format=format) == (True, 0)


def test_json_export_is_lossless_for_versioned_rules():
    rule = Rule(
        id="regex", semantic_version=2, action="replace", match_type="regex",
        stage="post", direction="s2t", source=r"term.+", target="word",
        scope="book", book_fingerprint="book-hash",
    )

    assert export_warnings((rule,), format="json") == (False, 0)
