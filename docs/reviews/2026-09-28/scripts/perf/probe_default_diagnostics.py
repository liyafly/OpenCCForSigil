#!/usr/bin/env python3
"""End-to-end plan time: default diagnostics as checked out vs two prototypes.

Prototype A replaces the per-character Han evidence count in
`core.diagnostics.diagnose_mixed_script` with a regex that yields the same count.
Prototype B additionally memoizes `convert_for_config(config, text)` for the
most recent text, so s2t requested by both the mixed-script diagnosis and the
classifier is converted once (official output is deterministic).
Plans are compared by digest. Synthetic data only.
"""

from __future__ import annotations

import hashlib
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synthetic_book import CountingBackend, SyntheticBook, build_sources  # noqa: E402

import core.diagnostics as diagnostics  # noqa: E402
from core.models import ConvertRequest  # noqa: E402
from core.workflow import ConversionWorkflow  # noqa: E402
from opencc_backend.backend import OpenCCBackend  # noqa: E402
from sigil.adapter import SigilBookAdapter  # noqa: E402

ORIGINAL = diagnostics.diagnose_mixed_script
_HAN = re.compile("[㐀-䶿一-鿿豈-﫿\U00020000-\U0002fa1f]+")


def _evidence(text):
    return sum(len(run) if run.isalpha() else sum(c.isalpha() for c in run)
               for run in _HAN.findall(text))


def prototype_diagnose(text, official_convert, *, min_evidence=2, include_outputs=False,
                       known_output_config=None, known_output=None):
    if not isinstance(text, str):
        raise TypeError("diagnostic input must be text")
    evidence_length = _evidence(text)
    if evidence_length < min_evidence:
        return diagnostics.ScriptDiagnostic(
            status="unknown", simplified_changed=False, traditional_changed=False,
            source_length=len(text), evidence_length=evidence_length,
            warning="insufficient Han text for script diagnosis")
    # Remaining body identical to the checked-out implementation.
    simplified = (known_output if known_output_config == "s2t" and known_output is not None
                  else diagnostics._invoke_official(official_convert, "s2t", text))
    traditional = (known_output if known_output_config == "t2s" and known_output is not None
                   else diagnostics._invoke_official(official_convert, "t2s", text))
    s_changed, t_changed = simplified != text, traditional != text
    if s_changed and t_changed:
        status, warning = "mixed", "current text contains mixed simplified and traditional evidence"
    elif s_changed:
        status, warning = "simplified", ""
    elif t_changed:
        status, warning = "traditional", ""
    else:
        status, warning = "unknown", "official conversions found no directional evidence"
    return diagnostics.ScriptDiagnostic(
        status=status, simplified_changed=s_changed, traditional_changed=t_changed,
        source_length=len(text), evidence_length=evidence_length, warning=warning,
        simplified_output=simplified if include_outputs else "",
        traditional_output=traditional if include_outputs else "")


class MemoBackend(CountingBackend):
    def __init__(self, backend):
        super().__init__(backend)
        self._memo = {}

    def convert_for_config(self, config, text):
        key = (config, text)
        if key in self._memo:
            return self._memo[key]
        if len(self._memo) > 8:
            self._memo.clear()
        value = super().convert_for_config(config, text)
        self._memo[key] = value
        return value


def digest(planned):
    value = hashlib.sha256()
    for item in planned:
        for change in item.plan.changes:
            value.update(repr(change).encode())
        for diagnostic in item.plan.diagnostics:
            value.update(repr(diagnostic).encode())
    return value.hexdigest()[:16]


def run(config, sources, mode, repeats=3):
    diagnostics.diagnose_mixed_script = ORIGINAL if mode == "current" else prototype_diagnose
    samples, result, backend = [], None, None
    for _ in range(repeats):
        raw = OpenCCBackend(config)
        backend = MemoBackend(raw) if mode == "evidence+memo" else CountingBackend(raw)
        workflow = ConversionWorkflow(SigilBookAdapter(SyntheticBook(sources)), backend,
                                      ConvertRequest(config))
        workflow.scan()
        start = time.perf_counter()
        result = workflow.plan()
        samples.append(time.perf_counter() - start)
    diagnostics.diagnose_mixed_script = ORIGINAL
    return statistics.median(samples), digest(result), backend.compare_calls


def main() -> int:
    sources = build_sources(200, 60, 150)
    for config in ("s2t", "s2twp"):
        digests = set()
        for mode in ("current", "evidence", "evidence+memo"):
            seconds, value, calls = run(config, sources, mode)
            digests.add(value)
            print(f"{config} {mode}: plan_median_seconds={seconds:.3f} compare_calls={calls} "
                  f"digest={value}")
        assert len(digests) == 1, "prototype changed the plan"
    print("identical_plans=True")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
