"""Compare patch assembly with the previous algorithm; synthetic, not host UI timing."""

import sys
import statistics
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugin" / "OpenCCForSigil"))
from core.models import TokenChange, SourceSpan
from core.staging import apply_changes, _validate_source_changes


def baseline(source, changes):
    _validate_source_changes(source, changes)
    result = source
    for change in sorted(changes, key=lambda item: (item.span.start, item.span.end), reverse=True):
        result = result[: change.span.start] + change.target + result[change.span.end :]
    return result


results = []
for size, count in [(10000, 100), (100000, 1000), (1000000, 3000)]:
    source = "汉" * size
    changes = tuple(
        TokenChange("汉", "漢字", SourceSpan(i, i + 1), "benchmark", change_id=str(i))
        for i in range(0, size, max(1, size // count))
    )
    times = {}
    for name, fn in [("baseline", baseline), ("current", apply_changes)]:
        samples = []
        for _ in range(3):
            start = time.perf_counter()
            value = fn(source, changes)
            samples.append(time.perf_counter() - start)
        times[name] = statistics.median(samples)
        if name == "baseline":
            expected = value
        else:
            assert value == expected
    results.append({"source_chars": size, "changes": len(changes), **times})
print(json.dumps(results, indent=2))
