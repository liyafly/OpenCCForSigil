from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from core.converter import OfficialBackendConverter
from core.models import ConvertRequest, RuleSnapshot as RequestRuleSnapshot
from core.workflow import ConversionWorkflow
from core.staging import apply_changes
from rules import matching
from rules.matching import RegexBudget, RuleExecutionError, collect_matches, replace_stage
from rules.models import Rule, RuleSnapshot
from rules.regex_runtime import load_regex_module
from rules.validators import RuleValidationError, validate_rules
from sigil.adapter import SigilBookAdapter


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

    def provenance(self):
        return SimpleNamespace(as_dict=lambda: {"backend": "test"})


class _Book:
    def __init__(self, sources):
        self.sources = dict(sources)

    def text_iter(self):
        return iter((identifier, f"{identifier}.xhtml") for identifier in self.sources)

    def readfile(self, identifier):
        return self.sources[identifier]

    def writefile(self, _identifier, _text):
        raise AssertionError("planning must not write files")


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


def test_zero_width_runtime_match_is_skipped_not_fatal():
    source = "他说「」然后「好」"
    rule = _rule(
        id="zero", source=r"(?<=「)[^」]*", target="善")

    result = OfficialBackendConverter(_Backend()).convert(source, _request((rule,)))

    assert result.target == "他说「」然后「善」"
    assert apply_changes(source, result.changes) == result.target
    assert result.zero_width_skips == (("zero", 1),)
    assert result.diagnostics == ()


def test_zero_width_skips_aggregate_to_one_diagnostic_per_rule_per_file():
    rule = _rule(id="z", source=r"(?<=「)[^」]*", target="…")
    source = "<html><body>" + "".join(
        "<p>他说「」然后「好」</p>" for _ in range(10)) + "</body></html>"
    sources = {f"chapter-{index:02d}": source for index in range(6)}

    planned = ConversionWorkflow(
        SigilBookAdapter(_Book(sources)), _Backend(), _request((rule,))).plan()

    assert len(planned) == 6
    for item in planned:
        diagnostics = [
            diagnostic for diagnostic in item.plan.diagnostics
            if diagnostic.code == "REGEX_ZERO_WIDTH_SKIPPED"]
        assert len(diagnostics) == 1
        assert diagnostics[0].message == "rule z: skipped 10 zero-width match(es)"
        assert "他说" not in diagnostics[0].message
        assert "「」" not in diagnostics[0].message
        assert "好" not in diagnostics[0].message


def test_skipped_candidate_trace_does_not_change_patches():
    earlier = Rule(
        id="g", source="大乾", target="G", direction="s2t", scope="global")
    later = Rule(
        id="b", source="乾隆帝", target="B", direction="s2t", scope="book",
        book_fingerprint="book-hash", priority=100_000)
    request = replace(
        _request((earlier, later)), book_fingerprint="book-hash")
    source = "大乾隆帝"

    plain = OfficialBackendConverter(_Backend()).convert(source, request)
    traced = OfficialBackendConverter(_Backend()).convert(
        source, replace(request, include_rule_trace=True))

    assert (traced.target, traced.changes) == (plain.target, plain.changes)
    assert plain.skipped_rule_trace == ()
    assert [(item.rule_id, item.winner_id, item.start, item.end)
            for item in traced.skipped_rule_trace] == [("b", "g", 1, 4)]


def test_regex_search_timeout_is_per_call_not_cumulative(monkeypatch):
    class Clock:
        value = 0.0

    class Pattern:
        def __init__(self):
            self.timeouts = []

        def search(self, _text, _position, *, timeout):
            self.timeouts.append(timeout)
            Clock.value += 0.5
            return None

    monkeypatch.setattr(
        matching, "time", SimpleNamespace(monotonic=lambda: Clock.value), raising=False)
    rules = tuple(_rule(id=f"slow-{index}", source="never") for index in range(8))
    patterns = {rule.id: Pattern() for rule in rules}

    assert collect_matches("x", rules, patterns, RegexBudget()) == ()
    assert all(pattern.timeouts == [0.05] for pattern in patterns.values())


def test_overlapping_regex_candidates_do_not_count_as_hits():
    rule = _rule(id="overlap", source=r"\p{Han}+", target="X")
    regex = load_regex_module()
    budget = RegexBudget()

    result, hits = replace_stage(
        "你好世界再见", (rule,), {rule.id: regex.compile(rule.source, regex.VERSION1)}, budget)

    assert result == "X"
    assert len(hits) == 1


def test_collapse_spaces_rule_plans_600_matches_across_60_files():
    rule = Rule.from_dict({
        "id": "collapse-spaces",
        "semantic_version": 2,
        "type": "exact",
        "action": "replace",
        "match_type": "regex",
        "stage": "post",
        "source": r"[ \t\u3000]{2,}",
        "target": " ",
        "direction": "*",
        "scope": "global",
    })
    snapshot = RuleSnapshot.freeze((rule,))
    request = ConvertRequest(
        "s2t",
        rules_snapshot=RequestRuleSnapshot(
            rules_hash=snapshot.sha256, rules=snapshot.rules),
        quotation_mode="keep",
        diagnose_mixed=False,
        detailed_classification=False,
    )
    sources = {
        f"chapter-{index:03d}": (
            "<html><body>" + "".join("<p>甲  乙</p>" for _ in range(10))
            + "</body></html>")
        for index in range(60)
    }

    planned = ConversionWorkflow(SigilBookAdapter(_Book(sources)), _Backend(), request).plan()

    assert len(planned) == 60
    assert sum(len(item.plan.changes) for item in planned) == 600


def test_runaway_regex_in_one_fragment_still_stops(monkeypatch):
    monkeypatch.setattr("rules.matching.REGEX_MAX_HITS_PER_RULE", 3)
    rule = _rule(id="runaway", source=r"\p{Han}", target="X")
    regex = load_regex_module()

    with pytest.raises(RuleExecutionError, match="runaway.*exceeded 3 hits"):
        replace_stage(
            "甲乙丙丁", (rule,), {rule.id: regex.compile(rule.source, regex.VERSION1)}, RegexBudget())


def test_single_regex_search_timeout_still_stops():
    rule = _rule(
        id="evil", source=r"(a|aa)+$", target="x", direction="s2t")
    regex = load_regex_module()

    with pytest.raises(RuleExecutionError, match="evil.*timed out"):
        replace_stage(
            "a" * 40 + "b",
            (rule,),
            {rule.id: regex.compile(rule.source, regex.VERSION1)},
            RegexBudget(),
        )


def test_regex_candidate_budget_is_per_rule_and_fragment(monkeypatch):
    monkeypatch.setattr("rules.matching.REGEX_MAX_CANDIDATES_PER_FRAGMENT", 2)
    rule = _rule(id="candidates", source=r".", target="X")
    regex = load_regex_module()

    with pytest.raises(RuleExecutionError, match="candidates.*more than 2 candidates"):
        collect_matches(
            "abc", (rule,), {rule.id: regex.compile(rule.source, regex.VERSION1)}, RegexBudget())


def test_regex_hits_are_limited_per_fragment_not_per_analysis():
    rule = _rule(id="many-fragments", source="x", target="y")
    budget = RegexBudget()

    for position in range(100_001):
        budget.note_regex_hit(rule, position, {})

    assert not hasattr(budget, "regex_hits")


def test_candidate_output_limit_resets_for_each_fragment():
    rule = _rule(id="fragment-output", source="x", target="1" * 1024)
    regex = load_regex_module()
    pattern = regex.compile(rule.source, regex.VERSION1)
    budget = RegexBudget()

    for _ in range(2_050):
        assert len(collect_matches("x", (rule,), {rule.id: pattern}, budget)) == 1
    assert not hasattr(budget, "candidate_output_chars")


def test_selected_output_has_no_analysis_wide_limit():
    target = "1" * 1_100_000
    rule = _rule(
        id="literal-output", match_type="literal", source="x", target=target)
    budget = RegexBudget()

    for _ in range(2):
        output, _hits = replace_stage("x", (rule,), {}, budget)
        assert output == target
    assert not hasattr(budget, "output_chars")


def test_optional_rule_trace_preserves_output_patches_and_reports_each_stage_hit():
    source = _rule(id="source", stage="source", action="override", source="s", target="S")
    pre = _rule(id="pre", stage="pre", source="a", target="b")
    post = _rule(id="post", stage="post", source="c", target="d")
    backend = _Backend()
    converter = OfficialBackendConverter(backend)
    plain = converter.convert("as c", _request((source, pre, post)))
    traced = OfficialBackendConverter(backend).convert(
        "as c", replace(_request((source, pre, post)), include_rule_trace=True))

    assert (traced.target, traced.changes) == (plain.target, plain.changes)
    assert traced.after_pre_rules == "bS c"
    assert traced.after_opencc == "bS c"
    assert traced.after_post_rules == "bS d"
    assert {(hit.rule_id, hit.stage, hit.source, hit.target)
            for hit in traced.rule_trace} == {
                ("source", "source", "s", "S"),
                ("pre", "pre", "a", "b"),
                ("post", "post", "c", "d"),
            }


def test_optional_rule_trace_keeps_a_match_whose_target_is_unchanged():
    same = _rule(id="same", stage="source", action="override", source="x", target="x")
    result = OfficialBackendConverter(_Backend()).convert(
        "x", replace(_request((same,)), include_rule_trace=True))

    assert result.target == "x"
    assert result.changes == ()
    assert len(result.rule_trace) == 1
    assert (result.rule_trace[0].source, result.rule_trace[0].target) == ("x", "x")


def test_malformed_rule_fields_are_reported_as_validation_errors():
    with pytest.raises(RuleValidationError, match="rule 0: action: action must be a string"):
        validate_rules(({"id": "bad", "action": [], "source": "x", "target": "y"},))


def test_zero_width_skip_inside_numeric_reference_is_reported():
    from document.tokenizer import TokenizerOptions

    rule = _rule(id="z", source=r"(?<=中)[^」]*", target="…")
    source = "<html><body><p>&#x4E2D;</p></body></html>"
    planned = ConversionWorkflow(
        SigilBookAdapter(_Book({"c": source})), _Backend(), _request((rule,)),
        tokenizer_options=TokenizerOptions(decode_numeric_cjk_refs=True),
    ).plan()

    diagnostics = [diagnostic for item in planned for diagnostic in item.plan.diagnostics
                   if diagnostic.code == "REGEX_ZERO_WIDTH_SKIPPED"]
    assert len(diagnostics) == 1
    assert "rule z" in diagnostics[0].message
