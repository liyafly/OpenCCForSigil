"""Round 1 (L-02): an unchanged ``>`` inside a long-text fallback block.

Baseline b2f674b re-escaped it to ``&gt;`` while verification still passed;
after the fix the raw ``>`` must be kept.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)

from check_quotes import plan_single
from core.models import ConvertRequest
from core.staging import StagingArea, apply_changes
from core.verifier import verify_staged_file

source = "<p>" + "汉" * 1500 + " a > b " + "汉" * 1500 + "</p>"
plan = plan_single(source, ConvertRequest("s2t"))
output = apply_changes(source, plan.changes)
print(
    "changes:", len(plan.changes), "has &gt;:", "&gt;" in output, "raw > kept:", " a > b " in output
)
staged = StagingArea().stage("a", source, plan)
print("verify passed:", verify_staged_file(staged).passed)
