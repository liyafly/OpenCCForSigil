from dataclasses import replace
from io import StringIO
import json

import pytest

from rules.exporters import export_rules, export_warnings
from rules.importers import import_rules
from rules.models import Rule, canonical_rules_json
from rules.validators import RuleValidationError
from tests.support.fake_qt import make_with_table
from ui import rules_window
from ui.i18n import Translator
from ui.rules_window import RuleManagerDialog, review_import


def test_json_import_keeps_rules_with_distinct_v2_semantics():
    base = Rule(
        id="pre", semantic_version=2, action="replace", stage="pre", source="term",
        target="word", direction="s2t",
    )
    variants = (
        replace(base, id="post", stage="post"),
        replace(base, id="regex", match_type="regex", source="term.+"),
        replace(base, id="disabled", enabled=False),
        replace(base, id="override", action="override", stage="source"),
        Rule(id="legacy", semantic_version=1, source="term", target="word", direction="s2t"),
    )

    result = import_rules(export_rules((base, *variants)), format="json")

    assert len(result.rules) == 6
    assert result.duplicates == ()
    assert {(rule.action, rule.match_type, rule.stage, rule.semantic_version, rule.enabled)
            for rule in result.rules} == {
                ("replace", "literal", "pre", 2, True),
                ("replace", "literal", "post", 2, True),
                ("replace", "regex", "pre", 2, True),
                ("replace", "literal", "pre", 2, False),
                ("override", "literal", "source", 2, True),
                ("override", "literal", "source", 1, True),
            }


def test_semantic_json_duplicates_are_removed_but_id_and_time_are_ignored():
    first = Rule(id="first", source="term", target="word", direction="s2t")
    second = replace(first, id="second", created_at="2026-01-01T00:00:00Z")

    result = import_rules(export_rules((first, second)), format="json")

    assert len(result.rules) == 1
    assert result.duplicates == (second,)


def test_import_review_uses_the_same_semantic_deduplication():
    first = Rule(id="first", semantic_version=2, action="replace", stage="pre",
                 source="term", target="word", direction="s2t")
    post = replace(first, id="post", stage="post")
    imported = import_rules(export_rules((first, post)), format="json")

    review = review_import((first,), imported)

    assert review.duplicate_count == 1
    assert tuple(rule.stage for rule in review.additions) == ("post",)


def test_tsv_import_uses_target_ruleset_semantic_version():
    source = "direction\tsource\ttarget\ns2t\t软件\t軟件\n"

    v2_rule = import_rules(source, format="tsv").rules[0]
    v1_rule = import_rules(source, format="tsv", semantic_version=1).rules[0]

    assert v2_rule.semantic_version == 2
    assert (v2_rule.action, v2_rule.match_type, v2_rule.stage) == (
        "override", "literal", "source")
    assert v1_rule.semantic_version == 1


def test_two_column_tsv_uses_selected_direction():
    result = import_rules(
        "软件\t軟件\n詞語\t詞彙\n", format="tsv", direction="s2t")

    assert [(rule.direction, rule.source, rule.target) for rule in result.rules] == [
        ("s2t", "软件", "軟件"), ("s2t", "詞語", "詞彙")]


def test_two_column_tsv_requires_an_explicit_direction():
    with pytest.raises(RuleValidationError) as captured:
        import_rules("软件\t軟件\n", format="tsv")

    assert captured.value.message_key == "rules.import_needs_direction"


def test_three_columns_without_direction_are_source_target_comment():
    result = import_rules(
        "软件\t軟件\tCommon term\n", format="tsv", direction="s2t")

    assert len(result.rules) == 1
    assert (result.rules[0].direction, result.rules[0].source,
            result.rules[0].target, result.rules[0].comment) == (
                "s2t", "软件", "軟件", "Common term")


def test_chinese_tsv_header_is_skipped():
    result = import_rules(" 源文本 \t目标文本\n软件\t軟件\n", format="tsv", direction="s2t")

    assert len(result.rules) == 1
    assert result.rules[0].source == "软件"
    assert [(item.line, item.severity, item.message_key) for item in result.diagnostics] == [
        (1, "info", "rules.import_header_skipped")]


@pytest.mark.parametrize("first_row", [
    "备注\t備註",
    "目标\t目標",
    "原文\t原文本",
    "source\tsauce",
])
def test_data_row_starting_with_header_word_is_not_skipped(first_row):
    result = import_rules(f"{first_row}\n软件\t軟體\n", format="tsv", direction="s2t")

    assert len(result.rules) == 2
    assert [(rule.source, rule.target) for rule in result.rules] == [
        tuple(first_row.split("\t")), ("软件", "軟體")]


def test_header_row_skip_is_reported_as_info():
    result = import_rules("源\t目标\n软件\t軟體\n", format="tsv", direction="s2t")

    assert len(result.rules) == 1
    assert [(item.line, item.severity, item.message_key) for item in result.diagnostics] == [
        (1, "info", "rules.import_header_skipped")]


def test_three_column_row_with_blank_direction_uses_selected_direction():
    result = import_rules("\t软件\t軟體\n", format="tsv", direction="s2t")

    assert [(rule.direction, rule.source, rule.target) for rule in result.rules] == [
        ("s2t", "软件", "軟體")]


def test_tsv_keeps_ascii_quotes_literally():
    result = import_rules(
        's2t\t"引号"\t"「引号」"\n', format="tsv")

    assert (result.rules[0].source, result.rules[0].target) == ('"引号"', '"「引号」"')


def test_tsv_unbalanced_quote_does_not_swallow_following_lines():
    result = import_rules(
        's2t\t"引号\t目标\ns2t\t第二行\t目标二\ns2t\t第三行\t目标三\n',
        format="tsv")

    assert [rule.source for rule in result.rules] == ['"引号', "第二行", "第三行"]


def test_tsv_export_import_roundtrip_with_quotes():
    original = Rule(
        id="quoted", source='包含 "引号"', target='改成 "目标"', comment='备注 "示例"',
        direction="s2t")

    exported = export_rules((original,), format="tsv")
    imported = import_rules(exported, format="tsv")

    assert len(imported.rules) == 1
    assert (imported.rules[0].source, imported.rules[0].target,
            imported.rules[0].comment) == (
            original.source, original.target, original.comment)


@pytest.mark.parametrize("separator", ["\u2028", "\u2029", "\x85"])
def test_tsv_roundtrip_keeps_unicode_line_separators(separator):
    original = Rule(
        id="r", direction="s2t", source="软件", target=f"軟{separator}體")

    imported = import_rules(export_rules((original,), format="tsv"), format="tsv")

    assert imported.rules[0].target == original.target
    assert [(item.severity, item.message_key) for item in imported.diagnostics] == [
        ("info", "rules.import_header_skipped")]


def test_tsv_roundtrip_keeps_form_feed_in_comment():
    original = Rule(
        id="r", direction="s2t", source="软件", target="軟體", comment="A\x0cB")

    imported = import_rules(export_rules((original,), format="tsv"), format="tsv")

    assert imported.rules[0].comment == original.comment


def test_opencc_txt_import_keeps_unicode_line_separators():
    target = "軟\u2028體"

    imported = import_rules(f"软件\t{target}\n", format="txt", direction="s2t")

    assert len(imported.rules) == 1
    assert imported.rules[0].target == target


def test_one_column_row_error_has_no_rule_prefix():
    imported = import_rules(
        "direction\tsource\ttarget\nonlyone\n", format="tsv", strict=False)

    error, = [item for item in imported.diagnostics if item.severity == "error"]
    assert error.line == 2
    assert not error.message.startswith("rule ")


@pytest.mark.parametrize("format,payload", [
    ("tsv", "软件\t軟體\n"),
    ("csv", "软件,軟體\n"),
    ("txt", "软件\t軟體\n"),
])
@pytest.mark.parametrize("scope", ["global", "profile", "book"])
def test_delimited_import_fills_only_matching_owner(format, payload, scope):
    imported = import_rules(
        payload,
        format=format,
        direction="s2t",
        scope=scope,
        profile_id="CURRENT-PROFILE",
        book_fingerprint="CURRENT-BOOK",
    )

    rule, = imported.rules
    assert rule.profile_id == ("CURRENT-PROFILE" if scope == "profile" else "")
    assert rule.book_fingerprint == ("CURRENT-BOOK" if scope == "book" else "")


def test_legacy_quoted_tsv_field_warns_but_stays_unchanged():
    raw_field = '"""引号"""'
    result = import_rules(f"s2t\t{raw_field}\t目标\n", format="tsv")

    assert result.rules[0].source == raw_field
    assert [(item.severity, item.message_key) for item in result.diagnostics] == [
        ("warning", "rules.import_tsv_quoted_field")]


def test_tsv_export_skips_fields_with_line_breaks_and_reports_count():
    safe = Rule(id="safe", source="术语", target="专名", direction="s2t")
    unsafe = Rule(id="unsafe", source="多行\n原文", target="目标", direction="s2t")

    exported = export_rules((safe, unsafe), format="tsv")

    assert "术语" in exported
    assert "多行" not in exported
    assert export_warnings((safe, unsafe), format="tsv") == (True, 1)


def test_csv_quotes_and_multiline_fields_keep_csv_behavior():
    payload = '"direction","source","target","comment"\n'
    payload += '"s2t","""引号""","目标","第一行\n第二行"\n'

    result = import_rules(payload, format="csv")

    assert len(result.rules) == 1
    assert result.rules[0].source == '"引号"'
    assert result.rules[0].comment == "第一行\n第二行"


def test_json_global_rule_roundtrip_keeps_empty_owner_fields():
    original = Rule(
        id="global", source="术语", target="专名", direction="s2t", scope="global")
    exported = export_rules((original,), format="json")

    imported = import_rules(
        exported, format="json", scope="book", profile_id="CURRENT-PROFILE",
        book_fingerprint="CURRENT-BOOK")

    assert canonical_rules_json(imported.rules) == canonical_rules_json((original,))


def test_json_selected_scope_applies_only_to_records_without_scope():
    payload = json.dumps([
        {"id": "global", "scope": "global", "direction": "s2t",
         "source": "全局", "target": "全域"},
        {"id": "foreign", "scope": "book", "book_fingerprint": "OTHER-BOOK",
         "direction": "s2t", "source": "外书", "target": "異書"},
        {"id": "defaulted", "direction": "s2t", "source": "默认", "target": "預設"},
    ], ensure_ascii=False)

    imported = import_rules(
        payload, format="json", scope="book", profile_id="CURRENT-PROFILE",
        book_fingerprint="CURRENT-BOOK")
    by_id = {rule.id: rule for rule in imported.rules}

    assert by_id["global"].scope == "global"
    assert (by_id["foreign"].scope, by_id["foreign"].book_fingerprint) == (
        "book", "OTHER-BOOK")
    assert (by_id["defaulted"].scope, by_id["defaulted"].book_fingerprint) == (
        "book", "CURRENT-BOOK")


def test_json_import_reports_foreign_owner_rules(monkeypatch):
    foreign = Rule(
        id="foreign-book", source="术语", target="專名", direction="s2t",
        scope="book", book_fingerprint="OTHER-BOOK")
    imported = import_rules(
        export_rules((foreign,), format="json"), format="json", scope="book",
        profile_id="CURRENT-PROFILE", book_fingerprint="CURRENT-BOOK")
    manager = RuleManagerDialog(
        make_with_table(), (), translator=Translator("en"), config="s2t",
        profile_id="CURRENT-PROFILE", book_fingerprint="CURRENT-BOOK")
    messages = []

    def capture_review(dialog):
        messages.append(dialog._layout.children[0].text())

    monkeypatch.setattr(rules_window, "exec_dialog", capture_review)
    manager._confirm_import(review_import((), imported))

    assert len(messages) == 1
    assert "1 rule(s) belong to another book or profile" in messages[0]


@pytest.mark.parametrize(("scope", "owner", "other_owner"), [
    ("book", "book_fingerprint", "OTHER-BOOK"),
    ("profile", "profile_id", "OTHER-PROFILE"),
])
def test_json_import_rebinds_foreign_owner_only_when_requested(scope, owner, other_owner):
    rule = Rule(
        id="foreign", source="术语", target="专名", direction="s2t", scope=scope,
        **{owner: other_owner})
    payload = export_rules((rule,), format="json")
    import_context = {
        "scope": scope,
        "profile_id": "CURRENT-PROFILE",
        "book_fingerprint": "CURRENT-BOOK",
    }

    unchanged = import_rules(payload, format="json", **import_context)
    rebound = import_rules(payload, format="json", rebind_owner=True, **import_context)

    assert getattr(unchanged.rules[0], owner) == other_owner
    assert getattr(rebound.rules[0], owner) == import_context[owner]
    other_owner_field = "profile_id" if owner == "book_fingerprint" else "book_fingerprint"
    assert getattr(rebound.rules[0], other_owner_field) == ""


@pytest.mark.parametrize(("payload", "format", "direction"), [
    ("direction\tsource\ttarget\n\n\n\n\nbad\t源\t目标\n", "tsv", None),
    ("direction,source,target\n\n\n\n\nbad,源,目标\n", "csv", None),
    ("#1\n#2\n#3\n#4\n#5\n\t目标\n", "txt", "s2t"),
])
def test_delimited_validation_errors_report_physical_line(payload, format, direction):
    result = import_rules(payload, format=format, direction=direction, strict=False)

    errors = [item for item in result.diagnostics if item.severity == "error"]
    assert len(errors) == 1
    assert errors[0].line == 6
    assert "rule 0" not in errors[0].message
    if format in {"tsv", "csv"}:
        assert [(item.line, item.severity, item.message_key)
                for item in result.diagnostics if item.severity == "info"] == [
                    (1, "info", "rules.import_header_skipped")]


def test_lenient_json_import_skips_bad_records_and_preserves_record_numbers():
    payload = [
        replacement_rule(id="first").to_dict(),
        {**replacement_rule(id="unknown").to_dict(), "unknown_field": True},
        "not a rule object",
        replacement_rule(id="last", source="末尾", target="尾部").to_dict(),
    ]
    result = import_rules(StringIO(json.dumps(payload)), format="json", strict=False)

    assert [rule.id for rule in result.rules] == ["first", "last"]
    assert [(item.line, item.location, item.severity) for item in result.diagnostics] == [
        (2, "record", "error"), (3, "record", "error")]
    assert "unknown rule fields" in result.diagnostics[0].message


def test_strict_json_import_fails_on_first_invalid_record_without_result():
    payload = [
        replacement_rule(id="first").to_dict(),
        {**replacement_rule(id="bad").to_dict(), "unknown_field": True},
        replacement_rule(id="last").to_dict(),
    ]

    with pytest.raises(RuleValidationError, match="rule 2: unknown rule fields"):
        import_rules(StringIO(json.dumps(payload)), format="json", strict=True)


@pytest.mark.parametrize("payload", ["{broken", "{\"rules\": {}}", "true"])
def test_lenient_json_import_still_rejects_broken_document_structure(payload):
    with pytest.raises((ValueError, json.JSONDecodeError)):
        import_rules(StringIO(payload), format="json", strict=False)


def replacement_rule(**values):
    return Rule.from_dict({
        "id": "rule", "source": "旧词", "target": "新词", "direction": "s2t",
        "semantic_version": 2, "action": "replace", "stage": "pre",
        "match_type": "literal", **values,
    })
