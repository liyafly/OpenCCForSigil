from __future__ import annotations

import json

import pytest

from rules.conflicts import BlockingRuleConflict, blocking_conflicts, find_conflicts
from rules.engine import convert_with_overlay, lock_spans
from rules.exporters import export_rules
from rules.importers import import_rules
from rules.models import Rule, RuleSnapshot
from rules.validators import RuleValidationError


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
    result = convert_with_overlay("这台服务器着火了", official, config="s2twp", snapshot=snapshot)
    assert result.final == "這臺服務器着火了"
    assert "服务器" not in "".join(calls)
    assert result.protected_spans[0].source == "着"


def test_direction_scope_and_disabled_rules():
    snapshot = RuleSnapshot.freeze(
        [
            Rule(direction="t2s", source="服务器", target="X"),
            Rule(direction="s2t", source="软件", target="Y", enabled=False),
            Rule(direction="s2t", source="软件", target="Z", scope="profile", profile_id="p"),
        ]
    )
    assert lock_spans("软件", snapshot, config="s2t", profile_id="other") == ()
    assert lock_spans("软件", snapshot, config="s2t", profile_id="p")[0].target == "Z"


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
        assert lock_spans("词", snapshot, config=direction)[0].target == "詞"
    snapshot = RuleSnapshot.freeze([Rule(direction="s2t", source="词", target="詞")])
    assert lock_spans("词", snapshot, config="s2t_jieba")[0].target == "詞"


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
        convert_with_overlay("服务器", lambda value: value, config="s2t", snapshot=snapshot)


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
    with pytest.raises(RuleValidationError, match="V1.1"):
        import_rules(
            json.dumps(
                {"rules": [{"type": "regex", "direction": "s2t", "source": "x", "target": "y"}]}
            )
        )
    original = RuleSnapshot.freeze([Rule(direction="s2t", source="a", target="b")])
    mutated = Rule(direction="s2t", source="a", target="c")
    assert original.rules[0].target == "b"
    assert original.sha256 != RuleSnapshot.freeze([mutated]).sha256


def test_segment_changes_reconstruct_exact_final_with_adjacent_length_changes():
    snapshot = RuleSnapshot.freeze([Rule(direction="s2t", source="术语", target="術語")])

    def official(value: str) -> str:
        return value.replace("一", "壹").replace("二", "貳")

    result = convert_with_overlay("一术语二", official, config="s2t", snapshot=snapshot)
    assert result.final == "壹術語貳"
    assert result.reconstruct() == result.final


def test_non_string_backend_output_is_rejected():
    snapshot = RuleSnapshot.freeze(())
    with pytest.raises(TypeError, match="must return str"):
        convert_with_overlay("软件", lambda value: None, config="s2t", snapshot=snapshot)


def test_repeated_protected_text_keeps_each_locked_boundary():
    snapshot = RuleSnapshot.freeze(
        [Rule(type="protect", direction="s2t", source="甲", target="甲")]
    )
    result = convert_with_overlay(
        "甲乙甲乙甲", lambda value: value.replace("乙", "乙字"), config="s2t", snapshot=snapshot
    )
    assert result.final == "甲乙字甲乙字甲"
    assert len(result.protected_spans) == 3
    assert result.reconstruct() == result.final


def test_snapshot_from_dict_checks_supplied_hash_and_requires_direction():
    snapshot = RuleSnapshot.freeze([Rule(direction="s2t", source="a", target="b")])
    payload = snapshot.to_dict()
    assert RuleSnapshot.from_dict(payload).sha256 == snapshot.sha256
    payload["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="sha256"):
        RuleSnapshot.from_dict(payload)
    with pytest.raises(RuleValidationError, match="direction"):
        import_rules('{"rules":[{"source":"a","target":"b"}]}')
