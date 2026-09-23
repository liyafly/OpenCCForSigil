import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)

from core.models import ConvertRequest, RuleSnapshot as RS
from core.converter import OfficialBackendConverter
from rules.models import Rule, RuleSnapshot


class B:
    config = "s2t"

    def convert(self, t):
        return t


a = RuleSnapshot.freeze((Rule(id="r", source="甲", target="乙", direction="s2t"),))
b_rules = (Rule(id="r", source="甲", target="丙", direction="s2t"),)
conv = OfficialBackendConverter(B())
r1 = conv.convert(
    "甲", ConvertRequest("s2t", rules_snapshot=RS(rules_hash=a.rules_hash, rules=a.rules))
)
print("first:", r1.target)
try:
    r2 = conv.convert(
        "甲", ConvertRequest("s2t", rules_snapshot=RS(rules_hash=a.rules_hash, rules=b_rules))
    )
    print(
        "second (tampered rules, same claimed hash):",
        r2.target,
        "-> no 'rule snapshot hash mismatch' raised",
    )
except ValueError as e:
    print("raised", e)
try:
    OfficialBackendConverter(B()).convert(
        "甲", ConvertRequest("s2t", rules_snapshot=RS(rules_hash=a.rules_hash, rules=b_rules))
    )
except ValueError as e:
    print("fresh converter raises:", e)
