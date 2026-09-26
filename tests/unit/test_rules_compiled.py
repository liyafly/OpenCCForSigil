import random

import pytest

from core.models import ConvertRequest, RuleSnapshot as RequestRuleSnapshot
from core.planner import build_conversion_plan
from document.tokenizer import tokenize_xhtml
from rules.conflicts import validate_no_blocking_conflicts
from rules.engine import LockedSpan, lock_spans
from rules.models import Rule, RuleSnapshot
from rules.precedence import applies_to, ordered_rules
from rules.validators import validate_snapshot


def _legacy_lock_spans(text, snapshot, *, config, profile_id=None, book_fingerprint=None):
    validate_snapshot(snapshot)
    conflicts = validate_no_blocking_conflicts(snapshot.rules)
    assert not any(conflict.blocking for conflict in conflicts)
    candidates = ordered_rules(
        rule for rule in snapshot.rules
        if applies_to(rule, config=config, profile_id=profile_id,
                      book_fingerprint=book_fingerprint)
    )
    spans = []
    cursor = 0
    while cursor < len(text):
        match = next((rule for rule in candidates if text.startswith(rule.source, cursor)), None)
        if match is None:
            cursor += 1
            continue
        end = cursor + len(match.source)
        target = match.source if match.type == "protect" else match.target
        spans.append(LockedSpan(cursor, end, match.source, target, match))
        cursor = end
    return tuple(spans)


def _random_rules(rng, count):
    rules = []
    source_heads = "词目汉字天地AB"
    for index in range(count):
        # Vary the first character so the index is exercised beyond one trie
        # bucket. Numeric suffixes also create overlapping prefixes (e.g. A1/A10).
        source = f"{rng.choice(source_heads)}x{index}"
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


def test_compiled_lock_spans_matches_legacy_ordering_for_300_random_snapshots():
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
        assert lock_spans(text, snapshot, config=config, profile_id="profile",
                          book_fingerprint="book") == _legacy_lock_spans(
                              text, snapshot, config=config, profile_id="profile",
                              book_fingerprint="book")


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
    assert len(overlay.index) == 3
    assert lock_spans_compiled(text, overlay) == _legacy_lock_spans(
        text, snapshot, config="s2t")
    spans = lock_spans_compiled(text, overlay)
    assert [(span.source, span.target) for span in spans] == [
        ("词语", "长"), ("目", "目标"), ("A", "alpha"),
    ]


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
