#!/usr/bin/env python3
"""Micro-probes for per-target overheads inside OfficialBackendConverter.convert.

1. Han evidence counting in diagnose_mixed_script (per-character generator vs a
   regex prototype that yields the identical count).
2. Duplicate comparison conversions for s2twp: s2t is requested by both the
   mixed-script diagnosis and the comparative classifier for the same text.
3. _positional_opcodes per-character loop vs a chunk-skipping prototype.
All prototypes are asserted equal to the checked-out functions. Synthetic data.
"""

from __future__ import annotations

import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synthetic_book import build_sources  # noqa: E402

from core import diagnostics as diag  # noqa: E402
from core.diff import _positional_opcodes  # noqa: E402
from document.tokenizer import tokenize_xhtml  # noqa: E402
from opencc_backend.backend import OpenCCBackend  # noqa: E402

_HAN = re.compile("[㐀-䶿一-鿿豈-﫿\U00020000-\U0002fa1f]+")


def evidence_prototype(text: str) -> int:
    count = 0
    for run in _HAN.findall(text):
        count += len(run) if run.isalpha() else sum(char.isalpha() for char in run)
    return count


def positional_prototype(source: str, target: str, chunk: int = 16):
    """Skip equal chunks with C-level slice comparison, then refine per character."""
    opcodes = []
    length = len(source)
    index = 0
    while index < length:
        same = source[index] == target[index]
        end = index + 1
        if same:
            while end + chunk <= length and source[end:end + chunk] == target[end:end + chunk]:
                end += chunk
        while end < length and (source[end] == target[end]) == same:
            end += 1
        opcodes.append(("equal" if same else "replace", index, end, index, end))
        index = end
    return tuple(opcodes)


def median(fn, repeats=5):
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - start)
    return statistics.median(samples)


def main() -> int:
    sources = build_sources(200, 60, 150)
    texts = [target.source_text for source in sources.values()
             for target in tokenize_xhtml(source).targets]
    print(f"targets={len(texts)} chars={sum(map(len, texts))}")

    current = [sum(char.isalpha() and diag._is_han(char) for char in text) for text in texts]
    assert current == [evidence_prototype(text) for text in texts]
    for sample in ("abc > !", "汉𠀀鿿\U0002a6dfＡ", "", "㐀䶿"):
        assert (sum(char.isalpha() and diag._is_han(char) for char in sample)
                == evidence_prototype(sample)), sample
    t_current = median(lambda: [sum(c.isalpha() and diag._is_han(c) for c in t) for t in texts])
    t_proto = median(lambda: [evidence_prototype(t) for t in texts])
    print(f"han_evidence current={t_current:.3f}s prototype={t_proto:.3f}s")

    backend = OpenCCBackend("s2twp")
    t_dup = median(lambda: [backend.convert_for_config("s2t", t) for t in texts], repeats=3)
    print(f"one extra s2t pass over all targets={t_dup:.3f}s (duplicated for s2twp/s2hkp)")

    s2t = OpenCCBackend("s2t")
    pairs = [(t, s2t.convert(t)) for t in texts]
    pairs = [(a, b) for a, b in pairs if len(a) == len(b) and a != b]
    assert all(_positional_opcodes(a, b) == positional_prototype(a, b) for a, b in pairs)
    t_pos = median(lambda: [_positional_opcodes(a, b) for a, b in pairs])
    t_pos2 = median(lambda: [positional_prototype(a, b) for a, b in pairs])
    print(f"positional_opcodes pairs={len(pairs)} current={t_pos:.3f}s prototype={t_pos2:.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
