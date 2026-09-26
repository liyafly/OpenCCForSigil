from dataclasses import replace
from io import StringIO
import json

import pytest

from rules.exporters import export_rules
from rules.importers import import_rules
from rules.models import Rule
from rules.validators import RuleValidationError
from ui.rules_window import review_import


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
