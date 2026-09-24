"""D-01: compare bounded_opcodes with a positional diff on equal-length outputs.

Prints the share of changed targets whose OpenCC output has the same length,
the time for both diffs, and one example where SequenceMatcher misaligns.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401

from book import make_book
from core.diff import bounded_opcodes
from document.tokenizer import tokenize_xhtml
from opencc_backend.backend import OpenCCBackend


def positional(source, target):
    ops, index = [], 0
    while index < len(source):
        end, same = index, source[index] == target[index]
        while end < len(source) and (source[end] == target[end]) == same:
            end += 1
        ops.append(("equal" if same else "replace", index, end, index, end))
        index = end
    return tuple(ops)


def spans(ops):
    return [op[1:] for op in ops if op[0] != "equal"]


files = make_book()
for config in ("s2t", "s2twp"):
    backend = OpenCCBackend(config)
    pairs = []
    for source in files.values():
        for target in tokenize_xhtml(source).targets:
            output = backend.convert(target.source_text)
            if output != target.source_text:
                pairs.append((target.source_text, output))
    same_length = [pair for pair in pairs if len(pair[0]) == len(pair[1])]
    start = time.perf_counter()
    old = [bounded_opcodes(s, o) for s, o in same_length]
    middle = time.perf_counter()
    new = [positional(s, o) for s, o in same_length]
    end = time.perf_counter()
    differing = [(a, b, p) for a, b, p in zip(old, new, same_length) if spans(a) != spans(b)]
    print(f"{config}: changed={len(pairs)} same-length={len(same_length)} "
          f"({100 * len(same_length) / max(1, len(pairs)):.1f}%) "
          f"bounded_opcodes={1000 * (middle - start):.0f} ms positional={1000 * (end - middle):.0f} ms "
          f"different-spans={len(differing)}")
    if differing:
        a, b, (s, o) = differing[0]
        only_old = sorted(set(spans(a)) - set(spans(b)))
        only_new = sorted(set(spans(b)) - set(spans(a)))
        print("  SequenceMatcher only:", [(s[i1:i2], o[j1:j2]) for i1, i2, j1, j2 in only_old][:4])
        print("  positional only     :", [(s[i1:i2], o[j1:j2]) for i1, i2, j1, j2 in only_new][:4])
    backend.close()
