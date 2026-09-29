# ruff: noqa: E401, E402, E701, E702, E731, F401, F811, F841
"""PERF-01 guard: prefix-indexed matching equals full scan (source/pre/post).

Run from the repository root. Read-only: uses temporary directories, never the user's data.
"""
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))
sys.path.insert(0, str(REPO))

import random, sys
from rules.compiled import CompiledOverlay, lock_spans_compiled
from rules.engine import LockedSpan
from rules.matching import RegexBudget, RuleExecutionError, replace_stage, source_matches
from rules.models import Rule, RuleSnapshot
from rules.validators import validate_rules
import inspect
STAGE_PARAMS = inspect.signature(replace_stage).parameters
A = "甲乙丙丁ab"
def outcome(fn):
    try: return ("ok", fn())
    except RuleExecutionError as e: return ("err", str(e))
mismatch = total = skipped = 0
for seed in range(3000):
    rng = random.Random(seed)
    rules = []
    for i in range(rng.randint(1, 25)):
        kind = rng.choice(("protect", "override", "pre", "post", "regex_src", "regex_pre", "v1"))
        src = "".join(rng.choice(A) for _ in range(rng.randint(1, 3)))
        tgt = "".join(rng.choice("XYZ") for _ in range(rng.randint(1, 2)))
        common = dict(id=f"r{i}", direction="s2t", priority=rng.randrange(-2, 3),
                      scope=rng.choice(("global", "profile")), profile_id="p")
        if kind == "v1":
            t = rng.choice(("exact", "protect"))
            rules.append(Rule(source=src, target=src if t == "protect" else tgt, type=t, **common))
        elif kind == "protect":
            rules.append(Rule(semantic_version=2, type="protect", action="protect", stage="source", source=src, target=src, **common))
        elif kind == "override":
            rules.append(Rule(semantic_version=2, action="override", stage="source", source=src, target=tgt, **common))
        elif kind in ("pre", "post"):
            rules.append(Rule(semantic_version=2, action="replace", stage=kind, source=src, target=tgt, **common))
        else:
            rules.append(Rule(semantic_version=2, action="override" if kind == "regex_src" else "replace",
                              stage="source" if kind == "regex_src" else "pre", match_type="regex",
                              source=rng.choice(("甲+", "[乙丙]", "a|b", "丁乙")), target=tgt, **common))
    try:
        snap = RuleSnapshot.freeze(tuple(rules))
        ov = CompiledOverlay.build(snap, config="s2t", profile_id="p")
    except Exception as exc:
        skipped += 1
        if skipped <= 3: print('skip', type(exc).__name__, str(exc)[:120])
        continue
    for _ in range(5):
        text = "".join(rng.choice(A + "的") for _ in range(rng.randint(0, 30)))
        total += 1
        fast = outcome(lambda: lock_spans_compiled(text, ov, RegexBudget()))
        slow = outcome(lambda: tuple(LockedSpan(m.start, m.end, text[m.start:m.end], m.target, m.rule)
                                     for m in source_matches(text, ov.source_rules, ov.regex_patterns, RegexBudget())))
        if fast != slow:
            mismatch += 1
            if mismatch <= 3: print("SRC", seed, text, fast, slow)
        for stage in ("pre", "post"):
            rs = getattr(ov, f"{stage}_rules")
            # Pass only the fast-path keywords that still exist, so this guard keeps
            # working after SIMP-02 removes regex_rules/include_single_char_rules.
            fast_kwargs = {"literal_index": getattr(ov, f"{stage}_literal_index"),
                           "order": getattr(ov, f"{stage}_rule_order")}
            if "regex_rules" in STAGE_PARAMS and hasattr(ov, f"{stage}_regex_rules"):
                fast_kwargs["regex_rules"] = getattr(ov, f"{stage}_regex_rules")
            if ("include_single_char_rules" in STAGE_PARAMS
                    and hasattr(ov, f"{stage}_has_single_char_literals")):
                fast_kwargs["include_single_char_rules"] = getattr(
                    ov, f"{stage}_has_single_char_literals")
            f2 = outcome(lambda: replace_stage(text, rs, ov.regex_patterns, RegexBudget(),
                                               **fast_kwargs))
            s2 = outcome(lambda: replace_stage(text, rs, ov.regex_patterns, RegexBudget()))
            if f2 != s2:
                mismatch += 1
                if mismatch <= 3: print(stage, seed, text, f2, s2)
print(f"texts={total} mismatches={mismatch} skipped_snapshots={skipped}")
