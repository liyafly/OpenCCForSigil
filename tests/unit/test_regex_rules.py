from __future__ import annotations

import pytest

from core.converter import OfficialBackendConverter
from core.models import ConvertRequest, RuleSnapshot as RequestRuleSnapshot
from core.staging import apply_changes
from rules.compiled import CompiledOverlay, lock_spans_compiled
from rules.matching import RegexBudget, RuleExecutionError
from rules.models import Rule, RuleSnapshot
from rules.templates import signature_protection
from rules.validators import RuleValidationError, validate_rules


class _Backend:
    config = "s2t"

    def __init__(self, substitutions=()):
        self.substitutions = tuple(substitutions)
        self.calls = []

    def convert(self, text):
        self.calls.append(text)
        for source, target in self.substitutions:
            text = text.replace(source, target)
        return text

    def convert_for_config(self, _config, text):
        return self.convert(text)


def _rule(**values):
    return Rule.from_dict({
        "semantic_version": 2,
        "type": "exact",
        "action": "replace",
        "match_type": "regex",
        "stage": "pre",
        "direction": "*",
        "scope": "global",
        **values,
    })


def _request(rules, *, punctuation="keep"):
    snapshot = RuleSnapshot.freeze(rules)
    return ConvertRequest(
        "s2t",
        rules_snapshot=RequestRuleSnapshot(
            rules_hash=snapshot.rules_hash,
            rules=snapshot.rules,
        ),
        punctuation_mode=punctuation,
        detailed_classification=False,
        diagnose_mixed=False,
    )


def test_signature_template_protects_marked_credit_and_horizontal_spacing():
    rule = Rule.from_dict({
        **signature_protection(),
        "id": "signature",
        "direction": "*",
        "scope": "global",
    })
    snapshot = RuleSnapshot.freeze((rule,))
    overlay = CompiledOverlay.build(snapshot, config="s2t")

    for source in ("◎著", "◎ 著", "◎  【著】", "◎\u3000著"):
        spans = lock_spans_compiled(source, overlay)
        assert [(span.source, span.target) for span in spans] == [(source, source)]
    assert lock_spans_compiled("普通的著作", overlay) == ()


def test_regex_final_wording_locks_actual_match_and_skips_backend():
    rule = Rule.from_dict({
        "id": "final",
        "semantic_version": 2,
        "type": "exact",
        "action": "override",
        "match_type": "regex",
        "stage": "source",
        "direction": "*",
        "scope": "global",
        "source": r"(?P<word>旧词)",
        "target": r"\g<word>术语",
    })
    backend = _Backend((("旧词", "OPENCC"),))

    result = OfficialBackendConverter(backend).convert(
        "前旧词后", _request((rule,)))

    assert result.target == "前旧词术语后"
    assert backend.calls == ["前", "后"]
    assert apply_changes("前旧词后", result.changes) == result.target


def test_pre_replacement_enters_opencc_then_post_runs_after_punctuation():
    pre = _rule(
        id="pre",
        source=r"(?P<term>旧)",
        target=r"\g<term>词",
    )
    post = Rule.from_dict({
        "id": "post",
        "semantic_version": 2,
        "type": "exact",
        "action": "replace",
        "match_type": "regex",
        "stage": "post",
        "direction": "*",
        "scope": "global",
        "source": r"(?P<comma>,)",
        "target": r"\g<comma>!",
    })
    source = "旧︐"
    backend = _Backend((("旧词", "繁词"),))

    result = OfficialBackendConverter(backend).convert(
        source, _request((pre, post), punctuation="horizontal"))

    assert backend.calls == ["旧词︐"]
    assert result.target == "繁词,!"
    assert apply_changes(source, result.changes) == result.target
    assert {change.rule_source for change in result.changes} == {"UserRule:post,pre"}
    assert result.changes[0].group_id.startswith("rules:")


def test_same_stage_replacements_do_not_cascade():
    first = _rule(id="first", match_type="literal", source="a", target="b")
    second = _rule(id="second", match_type="literal", source="b", target="c")
    result = OfficialBackendConverter(_Backend()).convert(
        "a", _request((first, second)))

    assert result.target == "b"
    assert apply_changes("a", result.changes) == "b"


def test_zero_width_pattern_and_bad_template_are_rejected():
    with pytest.raises(RuleValidationError, match="empty range"):
        validate_rules((_rule(id="zero", source=r"(?=x)", target="z"),))
    with pytest.raises(RuleValidationError, match="replacement template"):
        validate_rules((_rule(id="group", source=r"(?P<word>x)", target=r"\g<missing>"),))


def test_expired_regex_budget_stops_with_rule_identity():
    rule = _rule(id="bounded", source="x", target="y")
    budget = RegexBudget()
    budget.regex_seconds = 3.01

    with pytest.raises(RuleExecutionError, match="bounded.*budget"):
        budget.timeout_for(rule, 17)


@pytest.mark.parametrize("stage,action", [
    ("source", "override"), ("pre", "replace"), ("post", "replace")])
def test_replacement_output_budget_covers_every_stage(monkeypatch, stage, action):
    monkeypatch.setattr("rules.matching.REGEX_MAX_OUTPUT_CHARS_PER_RUN", 4)
    rule = _rule(id=stage, stage=stage, action=action, source="x", target="12345")

    with pytest.raises(RuleExecutionError, match=f"{stage}.*output"):
        OfficialBackendConverter(_Backend()).convert("x", _request((rule,)))


def test_replacement_output_budget_accepts_exact_limit_and_protect_does_not_use_it(
        monkeypatch):
    monkeypatch.setattr("rules.matching.REGEX_MAX_OUTPUT_CHARS_PER_RUN", 4)
    exact = _rule(id="exact", stage="source", action="override", source="x", target="1234")
    converter = OfficialBackendConverter(_Backend())
    assert converter.convert("x", _request((exact,))).target == "1234"

    protect = Rule.from_dict({
        "id": "protect", "type": "protect", "action": "protect",
        "match_type": "literal", "stage": "source", "direction": "*",
        "scope": "global", "source": "protected",
    })
    result = OfficialBackendConverter(_Backend()).convert("protected", _request((protect,)))
    assert result.target == "protected"


def test_a_new_converter_starts_a_fresh_rule_output_budget(monkeypatch):
    monkeypatch.setattr("rules.matching.REGEX_MAX_OUTPUT_CHARS_PER_RUN", 4)
    rule = _rule(id="bounded", stage="source", action="override", source="x", target="1234")

    for _ in range(2):
        assert OfficialBackendConverter(_Backend()).convert("x", _request((rule,))).target == "1234"


def test_malformed_rule_fields_are_reported_as_validation_errors():
    with pytest.raises(RuleValidationError, match="rule 0: action: action must be a string"):
        validate_rules(({"id": "bad", "action": [], "source": "x", "target": "y"},))
