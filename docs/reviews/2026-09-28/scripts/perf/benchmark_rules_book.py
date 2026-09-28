#!/usr/bin/env python3
"""Plan a synthetic large book with many literal rules; compare an indexed prototype.

Run from the repository root:

    mise exec -- uv run python <this script> --rules 2000

`current` runs the checked-out code. `indexed` monkeypatches this process only:

* `rules.compiled.lock_spans_compiled` derives the source-stage subset and a
  one/two-character literal prefix index once per overlay, then passes only the
  literal rules whose prefix occurs in the text (plus every regex rule, overlay
  order preserved) to the unchanged `rules.matching.source_matches`;
* `OfficialBackendConverter._convert_rules` is recompiled from the checked-out
  source with four per-call derivations hoisted (guarded flag, pre/post subsets,
  regex pattern dict) and the rule-free request cached per converter.

Both runs must produce an identical digest over every change and diagnostic.
The prototype rewrite targets the checked-out source at c14701f; after the real
fix lands use `--modes current` and compare the digest with the recorded one.
Synthetic data only; nothing is written.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import inspect
import random
import re
import statistics
import sys
import textwrap
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synthetic_book import CONVERTING, NEUTRAL, SyntheticBook, build_sources  # noqa: E402

import core.converter as converter_module  # noqa: E402
import rules.compiled as compiled  # noqa: E402
import rules.matching as matching  # noqa: E402
from core.models import ConvertRequest, RuleSnapshot as RequestRuleSnapshot  # noqa: E402
from core.workflow import ConversionWorkflow  # noqa: E402
from opencc_backend.backend import OpenCCBackend  # noqa: E402
from rules.engine import LockedSpan  # noqa: E402
from rules.models import Rule, RuleSnapshot  # noqa: E402
from sigil.adapter import SigilBookAdapter  # noqa: E402

ORIGINAL_COLLECT = matching.collect_matches
ORIGINAL_LOCK = compiled.lock_spans_compiled
ORIGINAL_CONVERT_RULES = converter_module.OfficialBackendConverter._convert_rules
CALLS = {"literal_rule_scans": 0}


def counting_collect(text, rules, regex_patterns, budget):
    CALLS["literal_rule_scans"] += sum(1 for rule in rules if rule.match_type == "literal")
    return ORIGINAL_COLLECT(text, rules, regex_patterns, budget)


_OVERLAY_PARTS: dict[int, tuple] = {}


def _overlay_parts(overlay):
    cached = _OVERLAY_PARTS.get(id(overlay))
    if cached is None or cached[0] is not overlay:
        source_rules = tuple(rule for rule in overlay.rules if rule.stage == "source")
        order = {rule.id: position for position, rule in enumerate(source_rules)}
        literal_index: dict[str, list] = {}
        for rule in source_rules:
            if rule.match_type == "literal" and rule.source:
                literal_index.setdefault(rule.source[:2], []).append(rule)
        regex_rules = tuple(rule for rule in source_rules if rule.match_type != "literal")
        cached = (overlay, literal_index, regex_rules, order, dict(overlay.regex_patterns))
        _OVERLAY_PARTS[id(overlay)] = cached
    return cached[1:]


def indexed_lock_spans(text, overlay, budget=None):
    budget = budget or matching.RegexBudget()
    literal_index, regex_rules, order, patterns = _overlay_parts(overlay)
    keys = set(text)
    keys.update(text[index:index + 2] for index in range(len(text) - 1))
    candidates = [rule for key in keys.intersection(literal_index)
                  for rule in literal_index[key]]
    candidates.sort(key=lambda rule: order[rule.id])
    candidates.extend(regex_rules)
    return tuple(
        LockedSpan(match.start, match.end, text[match.start:match.end], match.target, match.rule)
        for match in matching.source_matches(text, tuple(candidates), patterns, budget)
    )


def _build_hoisted_convert_rules():
    source = textwrap.dedent(inspect.getsource(ORIGINAL_CONVERT_RULES))
    replacements = (
        ('guarded_rules = any(rule.match_type == "regex" or rule.action == "replace" '
         'for rule in overlay.rules)',
         "guarded_rules, pre_rules, post_rules, regex_patterns = _stage_parts(overlay)"),
        ("unlocked = replace(request, rules_snapshot=type(request.rules_snapshot)())",
         "unlocked = _unlocked_request(self, request)"),
        ("regex_patterns = dict(overlay.regex_patterns)", "pass"),
        ('pre_rules = tuple(rule for rule in overlay.rules if rule.action == "replace" '
         'and rule.stage == "pre")', "pass"),
        ('post_rules = tuple(rule for rule in overlay.rules if rule.action == "replace" '
         'and rule.stage == "post")', "pass"),
    )
    for old, new in replacements:
        pattern = r"\s+".join(re.escape(part) for part in old.split())
        source, count = re.subn(pattern, lambda _match, new=new: new, source)
        assert count == 1, old

    stage_cache: dict[int, tuple] = {}

    def _stage_parts(overlay):
        cached = stage_cache.get(id(overlay))
        if cached is None or cached[0] is not overlay:
            cached = (overlay, (
                any(rule.match_type == "regex" or rule.action == "replace"
                    for rule in overlay.rules),
                tuple(rule for rule in overlay.rules
                      if rule.action == "replace" and rule.stage == "pre"),
                tuple(rule for rule in overlay.rules
                      if rule.action == "replace" and rule.stage == "post"),
                dict(overlay.regex_patterns),
            ))
            stage_cache[id(overlay)] = cached
        return cached[1]

    def _unlocked_request(converter, request):
        cached = getattr(converter, "_probe_unlocked", None)
        if cached is None or cached[0] is not request:
            cached = (request, dataclasses.replace(
                request, rules_snapshot=type(request.rules_snapshot)()))
            converter._probe_unlocked = cached
        return cached[1]

    namespace = dict(vars(converter_module))
    namespace.update(_stage_parts=_stage_parts, _unlocked_request=_unlocked_request)
    exec(compile(source, converter_module.__file__, "exec"), namespace)
    return namespace["_convert_rules"]


def make_rules(count: int, seed: int = 11):
    rng = random.Random(seed)
    pool = CONVERTING + NEUTRAL + "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥"
    seen: set[str] = set()
    rules = []
    while len(rules) < count:
        source = "".join(rng.choice(pool) for _ in range(rng.randint(2, 4)))
        if source in seen:
            continue
        seen.add(source)
        rules.append(Rule(id=f"r{len(rules):05d}", source=source,
                          target=source[::-1] if rng.random() < 0.5 else source,
                          direction="s2t", created_at="x", updated_at="x"))
    return tuple(rules)


def digest(planned):
    value = hashlib.sha256()
    for item in planned:
        for change in item.plan.changes:
            value.update(repr((change.change_id, change.span.start, change.span.end,
                               change.source, change.target, change.rule_source,
                               change.group_id, change.risk, change.category)).encode())
        for diagnostic in item.plan.diagnostics:
            value.update(repr(diagnostic).encode())
    return value.hexdigest()[:16]


def run(mode, sources, request, repeats):
    matching.collect_matches = counting_collect
    compiled.lock_spans_compiled = ORIGINAL_LOCK if mode == "current" else indexed_lock_spans
    converter_module.OfficialBackendConverter._convert_rules = (
        ORIGINAL_CONVERT_RULES if mode == "current" else _build_hoisted_convert_rules())
    samples, result = [], None
    try:
        for _ in range(repeats):
            CALLS["literal_rule_scans"] = 0
            workflow = ConversionWorkflow(SigilBookAdapter(SyntheticBook(sources)),
                                          OpenCCBackend("s2t"), request)
            workflow.scan()
            start = time.perf_counter()
            result = workflow.plan()
            samples.append(time.perf_counter() - start)
    finally:
        matching.collect_matches = ORIGINAL_COLLECT
        compiled.lock_spans_compiled = ORIGINAL_LOCK
        converter_module.OfficialBackendConverter._convert_rules = ORIGINAL_CONVERT_RULES
    return (statistics.median(samples), CALLS["literal_rule_scans"], digest(result),
            sum(len(item.plan.changes) for item in result))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rules", type=int, default=2000)
    parser.add_argument("--files", type=int, default=200)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--modes", default="current,indexed",
                        help="after the real fix lands, run with --modes current")
    args = parser.parse_args()
    sources = build_sources(args.files, 60, 150)
    frozen = RuleSnapshot.freeze(make_rules(args.rules))
    request = ConvertRequest("s2t", rules_snapshot=RequestRuleSnapshot(
        rules_hash=frozen.rules_hash, rules=frozen.rules))
    print(f"rules={args.rules} files={len(sources)} chars={sum(map(len, sources.values()))}")
    digests = {}
    for mode in args.modes.split(","):
        seconds, scans, value, changes = run(mode, sources, request, args.repeats)
        digests[mode] = value
        print(f"{mode}: plan_median_seconds={seconds:.3f} literal_rule_scans={scans} "
              f"changes={changes} digest={value}")
    assert len(set(digests.values())) == 1, "prototype changed the plan"
    print(f"identical_plans={len(digests) > 1}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
