import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)
import random

from tests.unit.test_rules_compiled import _legacy_lock_spans
from rules.engine import lock_spans
from rules.models import Rule, RuleSnapshot
from rules.conflicts import BlockingRuleConflict

rng = random.Random(7)
alpha = "甲乙丙丁ab"
checked = skipped = 0
for _ in range(2000):
    rules = []
    for i in range(rng.randrange(0, 60)):
        src = "".join(rng.choices(alpha, k=rng.randrange(1, 4)))
        if not any(c.isalpha() for c in src):
            continue
        t = rng.choice(("exact", "protect"))
        scope = rng.choice(("global", "profile", "book"))
        rules.append(
            Rule(
                id=f"r{i}",
                type=t,
                direction=rng.choice(("*", "s2t", "t2s")),
                source=src,
                target=src if t == "protect" else "".join(rng.choices("XYZ", k=2)),
                scope=scope,
                priority=rng.randrange(-2, 3),
                profile_id="p" if scope == "profile" else "",
                book_fingerprint="b" if scope == "book" else "",
                enabled=rng.random() > 0.1,
            )
        )
    snap = RuleSnapshot.freeze(rules)
    text = "".join(rng.choices(alpha, k=rng.randrange(0, 40)))
    try:
        old = _legacy_lock_spans(text, snap, config="s2t", profile_id="p", book_fingerprint="b")
    except BlockingRuleConflict:
        skipped += 1
        try:
            lock_spans(text, snap, config="s2t", profile_id="p", book_fingerprint="b")
            print("NEW DID NOT RAISE")
        except BlockingRuleConflict:
            pass
        continue
    new = lock_spans(text, snap, config="s2t", profile_id="p", book_fingerprint="b")
    assert new == old, (text, rules)
    checked += 1
print("equal:", checked, "conflict-raising both:", skipped)
