#!/usr/bin/env python3
"""Does the per-run regex time budget scale with book size?

Plans growing synthetic books with K rarely-matching regex rules and reports
the accumulated `RegexBudget.regex_seconds` (search time, not hits) and
whether planning fails with the 3-second run budget. Synthetic data only.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synthetic_book import SyntheticBook, build_sources  # noqa: E402

from core.converter import OfficialBackendConverter  # noqa: E402
from core.models import ConvertRequest, RuleSnapshot as RequestRuleSnapshot  # noqa: E402
from core.workflow import ConversionWorkflow  # noqa: E402
from opencc_backend.backend import OpenCCBackend  # noqa: E402
from rules.matching import RuleExecutionError  # noqa: E402
from rules.models import Rule, RuleSnapshot  # noqa: E402
from sigil.adapter import SigilBookAdapter  # noqa: E402

BUDGETS = []
_original_init = OfficialBackendConverter.__init__


def _tracking_init(self, backend):
    _original_init(self, backend)
    BUDGETS.append(self)


OfficialBackendConverter.__init__ = _tracking_init


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regex-rules", type=int, default=20)
    parser.add_argument("--files", default="10,50,100,200")
    args = parser.parse_args()
    rules = tuple(Rule(id=f"re{index}", semantic_version=2, action="replace", stage="pre",
                       match_type="regex", direction="s2t",
                       source=f"甲{index}[乙丙]+丁", target="戊",
                       created_at="x", updated_at="x")
                  for index in range(args.regex_rules))
    frozen = RuleSnapshot.freeze(rules)
    request = ConvertRequest("s2t", rules_snapshot=RequestRuleSnapshot(
        rules_hash=frozen.rules_hash, rules=frozen.rules),
        detailed_classification=False, diagnose_mixed=False)
    print("files targets regex_rules regex_seconds plan_seconds outcome")
    for files in (int(value) for value in args.files.split(",")):
        BUDGETS.clear()
        sources = build_sources(files, 60, 150)
        workflow = ConversionWorkflow(SigilBookAdapter(SyntheticBook(sources)),
                                      OpenCCBackend("s2t"), request)
        workflow.scan()
        start = time.perf_counter()
        try:
            planned = workflow.plan()
            outcome = "ok"
            targets = sum(len(item.tokenized.targets) for item in planned)
        except RuleExecutionError as exc:
            outcome = f"FAILED: {str(exc)[:70]}"
            targets = "-"
        elapsed = time.perf_counter() - start
        budget = BUDGETS[-1]._regex_budget
        print(files, targets, len(rules), f"{budget.regex_seconds:.3f}", f"{elapsed:.2f}",
              outcome)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
