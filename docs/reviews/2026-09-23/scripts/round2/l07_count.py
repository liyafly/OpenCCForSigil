import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)

import rules.validators as validators
import rules.compiled as compiled
from core.models import ConvertRequest, RuleSnapshot as RS
from core.planner import build_conversion_plan
from core.converter import OfficialBackendConverter
from document.tokenizer import tokenize_xhtml
from rules.models import Rule, RuleSnapshot

count = 0
orig = validators.validate_rules


def counted(r):
    global count
    count += 1
    return orig(r)


validators.validate_rules = counted

builds = 0
orig_build = compiled.CompiledOverlay.build.__func__


def counting_build(cls, *a, **k):
    global builds
    builds += 1
    return orig_build(cls, *a, **k)


compiled.CompiledOverlay.build = classmethod(counting_build)

snapshot = RuleSnapshot.freeze((Rule(id="rule", source="专名", target="專名", direction="s2t"),))


class Backend:
    config = "s2t"

    def convert(self, t):
        return t.replace("汉", "漢")

    def convert_for_config(self, c, t):
        return t

    def provenance(self):
        return type("P", (), {"as_dict": lambda s: {}})()


src = "".join("<p>汉</p>" for _ in range(50))
req = ConvertRequest("s2t", rules_snapshot=RS(rules_hash=snapshot.rules_hash, rules=snapshot.rules))
build_conversion_plan(
    file_id="a", source=src, document=tokenize_xhtml(src), backend=Backend(), request=req
)
print("validate_rules counted (as test does):", count, "actual overlay builds:", builds)

# Simulate regression: disable cache -> build per node
count = 0
builds = 0
orig_init = OfficialBackendConverter.__init__


class NoCache(dict):
    def __setitem__(self, k, v):
        pass


def init(self, backend):
    orig_init(self, backend)
    self._compiled_overlays = NoCache()


OfficialBackendConverter.__init__ = init
build_conversion_plan(
    file_id="a", source=src, document=tokenize_xhtml(src), backend=Backend(), request=req
)
print(
    "with cache disabled -> validate_rules counted:",
    count,
    "overlay builds:",
    builds,
    "(test assertion count<=3 would still pass)",
)
