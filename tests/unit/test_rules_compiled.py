import random
import inspect
from dataclasses import fields
from importlib.util import find_spec

import pytest

from core.models import ConvertRequest, RuleSnapshot as RequestRuleSnapshot
from core.planner import build_conversion_plan
from document.tokenizer import tokenize_xhtml
from rules.conflicts import validate_no_blocking_conflicts
from rules.compiled import CompiledOverlay, LockedSpan, lock_spans_compiled
from rules.models import Rule, RuleSnapshot
from rules.precedence import applies_to, ordered_rules
from rules.validators import validate_snapshot


def test_legacy_rules_engine_pipeline_and_exports_are_removed():
    import rules

    assert find_spec("rules.engine") is None
    assert not hasattr(rules, "convert_with_overlay")
    assert not hasattr(rules, "lock_spans")


def test_simp07_removes_unmeasured_matcher_fast_paths():
    from core.converter import OfficialBackendConverter
    from rules.compiled import CompiledOverlay, lock_spans_compiled
    from rules.matching import replace_stage

    assert "candidate_cache" not in inspect.signature(lock_spans_compiled).parameters
    stage_parameters = set(inspect.signature(replace_stage).parameters)
    assert stage_parameters == {
        "text", "rules", "regex_patterns", "budget", "literal_index", "order", "skipped",
    }
    overlay_fields = {item.name for item in fields(CompiledOverlay)}
    assert not any(name.endswith(("_regex_rules", "_has_single_char_literals"))
                   for name in overlay_fields)
    converter = OfficialBackendConverter(object())
    assert not hasattr(converter, "_source_candidate_cache")
    assert converter._unlocked_request is None


def _reference_lock_spans(text, snapshot, *, config, profile_id=None, book_fingerprint=None):
    validate_snapshot(snapshot)
    conflicts = validate_no_blocking_conflicts(snapshot.rules)
    assert not any(conflict.blocking for conflict in conflicts)
    candidates = ordered_rules(
        rule for rule in snapshot.rules
        if applies_to(rule, config=config, profile_id=profile_id,
                      book_fingerprint=book_fingerprint)
    )
    # FIX A-08 changed source locking so any exact match that overlaps a
    # protection span is skipped, even when the exact match starts earlier.
    # Reserve protections in their own left-to-right pass before scanning the
    # remaining candidates, matching the documented production semantics.
    protections = []
    cursor = 0
    while cursor < len(text):
        match = next((rule for rule in candidates
                      if rule.type == "protect" and text.startswith(rule.source, cursor)), None)
        if match is None:
            cursor += 1
            continue
        end = cursor + len(match.source)
        protections.append(LockedSpan(cursor, end, match.source, match.source, match))
        cursor = end
    spans = []
    cursor = 0
    protection_index = 0
    while cursor < len(text):
        while (protection_index < len(protections)
               and protections[protection_index].end <= cursor):
            protection_index += 1
        if (protection_index < len(protections)
                and protections[protection_index].start == cursor):
            protection = protections[protection_index]
            spans.append(protection)
            cursor = protection.end
            continue
        match = None
        for rule in candidates:
            if not text.startswith(rule.source, cursor):
                continue
            end = cursor + len(rule.source)
            overlaps_protection = any(
                cursor < protection.end and end > protection.start
                for protection in protections
            )
            if not overlaps_protection:
                match = rule
                break
        if match is None:
            cursor += 1
            continue
        end = cursor + len(match.source)
        spans.append(LockedSpan(cursor, end, match.source, match.target, match))
        cursor = end
    return tuple(spans)


def _random_rules(rng, count, *, exclude=()):
    rules = []
    alphabet = "词语深目汉字A012"
    used_sources = set(exclude)
    for index in range(count):
        while True:
            source = "".join(rng.choice(alphabet) for _ in range(rng.randrange(1, 4)))
            if source not in used_sources:
                used_sources.add(source)
                break
        rule_type = rng.choice(("exact", "protect"))
        scope = rng.choice(("global", "profile", "book"))
        rules.append(Rule(
            id=f"r{index}",
            enabled=rng.choice((True, True, False)),
            type=rule_type,
            direction=rng.choice(("*", "s2t", "t2s")),
            source=source,
            target=source if rule_type == "protect" else f"目{index}",
            scope=scope,
            priority=rng.randrange(-5, 6),
            profile_id="profile" if scope == "profile" else "",
            book_fingerprint="book" if scope == "book" else "",
        ))
    return tuple(rules)


def test_compiled_lock_spans_matches_reference_ordering_for_300_random_snapshots():
    from rules.matching import RegexBudget, source_matches

    rng = random.Random(20260923)
    alphabet = "词目汉字"
    for _ in range(300):
        rules = _random_rules(rng, rng.randrange(201))
        snapshot = RuleSnapshot.freeze(rules)
        usable_sources = tuple(rule.source for rule in rules if rule.enabled)
        parts = [rng.choice(usable_sources) if usable_sources and rng.random() < 0.45
                 else rng.choice(alphabet) for _ in range(rng.randrange(1, 25))]
        text = "".join(parts)
        config = rng.choice(("s2t", "t2s"))
        overlay = CompiledOverlay.build(
            snapshot, config=config, profile_id="profile", book_fingerprint="book")
        expected = tuple(
            LockedSpan(match.start, match.end, text[match.start:match.end],
                       match.target, match.rule)
            for match in source_matches(
                text, overlay.source_rules, overlay.regex_patterns, RegexBudget())
        )
        assert lock_spans_compiled(text, overlay) == expected


def test_rule_snapshot_is_validated_once_for_a_multi_file_plan(monkeypatch):
    import rules.compiled as compiled

    count = 0
    original = compiled.validate_rules

    def counted(rules):
        nonlocal count
        count += 1
        return original(rules)

    monkeypatch.setattr(compiled, "validate_rules", counted)
    snapshot = RuleSnapshot.freeze((Rule(id="rule", source="专名", target="專名",
                                         direction="s2t"),))

    class Backend:
        config = "s2t"

        def convert(self, text):
            return text.replace("汉", "漢")

        def convert_for_config(self, _config, text):
            return text

        def provenance(self):
            return type("P", (), {"as_dict": lambda _self: {}})()

    source = "".join("<p>汉</p>" for _ in range(50))
    request = ConvertRequest("s2t", rules_snapshot=RequestRuleSnapshot(
        rules_hash=snapshot.rules_hash, rules=snapshot.rules))
    build_conversion_plan(file_id="a", source=source, document=tokenize_xhtml(source),
                          backend=Backend(), request=request)

    assert count == 1


def test_compiled_overlay_covers_prefixes_buckets_disabled_rules_and_conflicts():
    from rules.compiled import CompiledOverlay, lock_spans_compiled
    from rules.conflicts import find_conflicts

    rules = (
        Rule(id="prefix-short", source="词", target="短", direction="s2t"),
        Rule(id="prefix-long", source="词语", target="长", direction="s2t"),
        Rule(id="other-bucket", source="目", target="目标", direction="s2t"),
        Rule(id="disabled-long", enabled=False, source="词语深", target="错误",
             direction="s2t"),
        Rule(id="duplicate-a", source="A", target="alpha", direction="s2t"),
        Rule(id="duplicate-b", source="A", target="alpha", direction="s2t"),
        Rule(id="disabled-conflict", enabled=False, source="A", target="wrong",
             direction="s2t"),
    )
    snapshot = RuleSnapshot.freeze(rules)
    conflicts = find_conflicts(rules)
    assert [(item.kind, item.source, item.blocking) for item in conflicts] == [
        ("DUPLICATE", "A", False),
    ]

    overlay = CompiledOverlay.build(snapshot, config="s2t")
    text = "词语深目A"
    assert set(overlay.source_literal_index) == {"词", "词语", "目", "A"}
    assert lock_spans_compiled(text, overlay) == _reference_lock_spans(
        text, snapshot, config="s2t")
    spans = lock_spans_compiled(text, overlay)
    assert [(span.source, span.target) for span in spans] == [
        ("词语", "长"), ("目", "目标"), ("A", "alpha"),
    ]


def test_prefix_indexed_lock_spans_equals_full_scan_for_300_random_snapshots():
    from rules.compiled import CompiledOverlay, lock_spans_compiled
    from rules.matching import RegexBudget, source_matches

    rng = random.Random(20260928)
    explicit_rules = (
        Rule(id="one-character", source="词", target="字", direction="s2t"),
        Rule(id="overlap-short", source="词语", target="短", direction="s2t"),
        Rule(id="overlap-long", source="词语深", target="长", direction="s2t"),
        Rule(id="letter", source="A", target="甲", direction="s2t"),
        Rule(id="letter-prefix", source="A1", target="乙", direction="s2t"),
        Rule(id="letter-overlap", source="A10", target="丙", direction="s2t"),
        Rule(
            id="regex-source",
            semantic_version=2,
            action="override",
            match_type="regex",
            stage="source",
            source=r"字\d+",
            target="数字",
            direction="s2t",
        ),
    )
    alphabet = "词语深目汉字A012"
    for _ in range(300):
        rules = (*_random_rules(
            rng, rng.randrange(201), exclude=tuple(rule.source for rule in explicit_rules)),
            *explicit_rules)
        snapshot = RuleSnapshot.freeze(rules)
        overlay = CompiledOverlay.build(
            snapshot, config="s2t", profile_id="profile", book_fingerprint="book")
        text = "".join(rng.choice(alphabet) for _ in range(rng.randrange(1, 50)))
        text += rng.choice(("词语深", "A10", "字12", "词", "普通"))
        matches = source_matches(
            text, overlay.source_rules, overlay.regex_patterns, RegexBudget())
        expected = tuple(
            LockedSpan(match.start, match.end, text[match.start:match.end],
                       match.target, match.rule)
            for match in matches
        )

        assert lock_spans_compiled(text, overlay) == expected


def test_prefix_indexed_replace_stage_equals_full_scan_for_random_rules():
    from rules.compiled import CompiledOverlay, lock_spans_compiled
    from rules.matching import RegexBudget, RuleExecutionError, replace_stage, source_matches

    alphabet = "甲乙丙丁ab"

    def outcome(call):
        try:
            return "ok", call()
        except RuleExecutionError as exc:
            return "error", str(exc)

    for seed in range(300):
        rng = random.Random(seed)
        rules = []
        for index in range(rng.randint(1, 25)):
            kind = rng.choice(("protect", "override", "pre", "post",
                               "regex_src", "regex_pre", "v1"))
            source = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 3)))
            target = "".join(rng.choice("XYZ") for _ in range(rng.randint(1, 2)))
            common = dict(
                id=f"r{index}", direction="s2t", priority=rng.randrange(-2, 3),
                scope=rng.choice(("global", "profile")), profile_id="p")
            if kind == "v1":
                rule_type = rng.choice(("exact", "protect"))
                rules.append(Rule(
                    source=source,
                    target=source if rule_type == "protect" else target,
                    type=rule_type,
                    **common,
                ))
            elif kind == "protect":
                rules.append(Rule(
                    semantic_version=2, type="protect", action="protect", stage="source",
                    source=source, target=source, **common,
                ))
            elif kind == "override":
                rules.append(Rule(
                    semantic_version=2, action="override", stage="source",
                    source=source, target=target, **common,
                ))
            elif kind in ("pre", "post"):
                rules.append(Rule(
                    semantic_version=2, action="replace", stage=kind,
                    source=source, target=target, **common,
                ))
            else:
                rules.append(Rule(
                    semantic_version=2,
                    action="override" if kind == "regex_src" else "replace",
                    stage="source" if kind == "regex_src" else "pre",
                    match_type="regex",
                    source=rng.choice(("甲+", "[乙丙]", "a|b", "丁乙")),
                    target=target,
                    **common,
                ))

        try:
            snapshot = RuleSnapshot.freeze(tuple(rules))
            overlay = CompiledOverlay.build(
                snapshot, config="s2t", profile_id="p")
        except (RuleExecutionError, ValueError):
            continue

        for _ in range(5):
            text = "".join(rng.choice(alphabet + "的")
                           for _ in range(rng.randint(0, 30)))
            fast_source = outcome(
                lambda: lock_spans_compiled(text, overlay, RegexBudget()))
            def full_source():
                matches = source_matches(
                    text, overlay.source_rules, overlay.regex_patterns, RegexBudget())
                return tuple(LockedSpan(
                    match.start, match.end, text[match.start:match.end],
                    match.target, match.rule) for match in matches)
            assert fast_source == outcome(full_source), (seed, "source", text)

            for stage in ("pre", "post"):
                stage_rules = getattr(overlay, f"{stage}_rules")
                fast_kwargs = {
                    "literal_index": getattr(overlay, f"{stage}_literal_index"),
                    "order": getattr(overlay, f"{stage}_rule_order"),
                }
                fast_stage = outcome(lambda: replace_stage(
                    text, stage_rules, overlay.regex_patterns, RegexBudget(), **fast_kwargs))
                full_stage = outcome(lambda: replace_stage(
                    text, stage_rules, overlay.regex_patterns, RegexBudget()))
                assert fast_stage == full_stage, (seed, stage, text)


def test_lock_spans_passes_only_prefix_candidates(monkeypatch):
    import rules.matching as matching
    from rules.compiled import CompiledOverlay, lock_spans_compiled

    regex_rule = Rule(
        id="regex-source",
        semantic_version=2,
        action="override",
        match_type="regex",
        stage="source",
        source="不存在",
        target="never",
        direction="s2t",
    )
    rules = tuple(
        Rule(id=f"literal-{index}", source=f"甲乙{index}", target="目标",
             direction="s2t")
        for index in range(2_000)
    ) + (regex_rule,)
    overlay = CompiledOverlay.build(RuleSnapshot.freeze(rules), config="s2t")
    seen = []
    original_collect = matching.collect_matches

    def record_candidates(text, candidates, regex_patterns, budget):
        seen.append(tuple(candidates))
        return original_collect(text, candidates, regex_patterns, budget)

    monkeypatch.setattr(matching, "collect_matches", record_candidates)

    assert lock_spans_compiled("漢字" * 50, overlay) == ()

    assert len(seen) == 1
    assert not any(rule.match_type == "literal" for rule in seen[0])
    assert tuple(rule for rule in seen[0] if rule.match_type == "regex") == (regex_rule,)


def test_convert_rules_does_not_iterate_overlay_rules_per_target():
    from core.converter import OfficialBackendConverter

    class Backend:
        config = "s2t"

        def convert(self, text):
            return text

        def convert_for_config(self, _config, text):
            return text

        def provenance(self):
            return type("P", (), {"as_dict": lambda _self: {}})()

    snapshot = RuleSnapshot.freeze((Rule(
        id="common-name", source="专名", target="專名", direction="s2t"),))
    request = ConvertRequest(
        "s2t", rules_snapshot=RequestRuleSnapshot(
            rules_hash=snapshot.rules_hash, rules=snapshot.rules))
    converter = OfficialBackendConverter(Backend())
    converter.convert("专名", request)
    overlay = next(value[1] for value in converter._compiled_overlays.values())
    iterations = 0

    class CountingTuple(tuple):
        def __iter__(self):
            nonlocal iterations
            iterations += 1
            return super().__iter__()

    object.__setattr__(overlay, "rules", CountingTuple(overlay.rules))
    for index in range(100):
        converter.convert(f"第{index}次 专名", request)

    assert iterations == 0


def test_compiled_overlay_rejects_mismatched_requested_hash():
    from rules.compiled import CompiledOverlay

    snapshot = RuleSnapshot.freeze((Rule(id="rule", source="词", target="詞",
                                         direction="s2t"),))
    with pytest.raises(ValueError, match="^rule snapshot hash mismatch$"):
        CompiledOverlay.build(snapshot, expected_hash="0" * 64, config="s2t")


def test_conflicts_in_an_unselected_direction_do_not_block_this_run():
    from rules.compiled import CompiledOverlay
    from rules.conflicts import BlockingRuleConflict

    snapshot = RuleSnapshot.freeze((
        Rule(id="s2t-one", source="同词", target="甲", direction="s2t"),
        Rule(id="s2t-two", source="同词", target="乙", direction="s2t"),
    ))

    assert CompiledOverlay.build(snapshot, config="t2s").rules == ()
    with pytest.raises(BlockingRuleConflict):
        CompiledOverlay.build(snapshot, config="s2t")


def test_protect_rule_wins_over_earlier_overlapping_exact_match():
    from rules.compiled import CompiledOverlay, lock_spans_compiled

    snapshot = RuleSnapshot.freeze((
        Rule(id="protect", type="protect", source="乾隆", direction="s2t"),
        Rule(id="exact", source="大乾", target="大幹", direction="s2t"),
    ))
    overlay = CompiledOverlay.build(snapshot, config="s2t")

    spans = lock_spans_compiled("大乾隆帝", overlay)

    assert any(span.source == "乾隆" and span.target == "乾隆" for span in spans)
    assert not any(span.source == "大乾" for span in spans)


def test_shorter_override_at_same_start_survives_overlapping_protect():
    from rules.compiled import CompiledOverlay, lock_spans_compiled

    snapshot = RuleSnapshot.freeze((
        Rule(id="protect", type="protect", source="乾隆", direction="s2t"),
        Rule(id="long", source="大乾", target="大幹", direction="s2t"),
        Rule(id="short", source="大", target="太", direction="s2t"),
    ))
    overlay = CompiledOverlay.build(snapshot, config="s2t")

    spans = lock_spans_compiled("大乾隆", overlay)

    assert [span.source for span in spans] == ["大", "乾隆"]
    assert [span.target for span in spans] == ["太", "乾隆"]


def test_exact_rule_still_matches_when_it_does_not_overlap_a_protect_span():
    from rules.compiled import CompiledOverlay, lock_spans_compiled

    snapshot = RuleSnapshot.freeze((
        Rule(id="protect", type="protect", source="乾隆", direction="s2t"),
        Rule(id="exact", source="大乾", target="大幹", direction="s2t"),
    ))
    overlay = CompiledOverlay.build(snapshot, config="s2t")

    spans = lock_spans_compiled("大乾坤", overlay)

    assert [(span.source, span.target) for span in spans] == [("大乾", "大幹")]


def test_converter_revalidates_a_different_rules_tuple_for_a_cached_hash():
    from core.converter import OfficialBackendConverter

    class Backend:
        config = "s2t"

        def convert(self, text):
            return text

        def convert_for_config(self, _config, text):
            return text

    first = RuleSnapshot.freeze((Rule(id="one", source="来源", target="來源",
                                      direction="s2t"),))
    second = RuleSnapshot.freeze((Rule(id="two", source="来源", target="源頭",
                                       direction="s2t"),))
    converter = OfficialBackendConverter(Backend())
    converter.convert("来源", ConvertRequest(
        "s2t", rules_snapshot=RequestRuleSnapshot(
            rules_hash=first.rules_hash, rules=first.rules)))

    request_with_forged_cache_hit = ConvertRequest(
        "s2t", rules_snapshot=RequestRuleSnapshot(
            rules_hash=first.rules_hash, rules=second.rules))
    with pytest.raises(ValueError, match="^rule snapshot hash mismatch$"):
        converter.convert("来源", request_with_forged_cache_hit)


@pytest.mark.parametrize("use_worker", [False, True])
def test_rule_overlay_is_built_once_per_workflow_plan_across_files(monkeypatch, use_worker):
    from types import SimpleNamespace

    from core.workflow import ConversionWorkflow
    from rules.compiled import CompiledOverlay
    from sigil.adapter import SigilBookAdapter

    class Backend:
        config = "s2t"

        def convert(self, text):
            return text

        def convert_for_config(self, _config, text):
            return text

        def provenance(self):
            return SimpleNamespace(as_dict=lambda: {"backend": "identity"})

        def close(self):
            pass

    class Book:
        def text_iter(self):
            yield "one", "one.xhtml"
            yield "two", "two.xhtml"

        def readfile(self, file_id):
            return f"<p>{file_id} 专名</p>"

    snapshot = RuleSnapshot.freeze((Rule(id="name", source="专名", target="專名",
                                         direction="s2t"),))
    request = ConvertRequest(
        "s2t", rules_snapshot=RequestRuleSnapshot(
            rules_hash=snapshot.rules_hash, rules=snapshot.rules),
        diagnose_mixed=False, detailed_classification=False,
    )
    calls = 0
    original_build = CompiledOverlay.build.__func__

    def counted_build(cls, *args, **kwargs):
        nonlocal calls
        calls += 1
        return original_build(cls, *args, **kwargs)

    monkeypatch.setattr(CompiledOverlay, "build", classmethod(counted_build))
    workflow = ConversionWorkflow(SigilBookAdapter(Book()), Backend(), request)
    if use_worker:
        workflow.plan_in_worker(lambda _config: Backend())
    else:
        workflow.plan()

    assert calls == 1
