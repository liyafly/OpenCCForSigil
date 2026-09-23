import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)
import time

t = time.perf_counter()
from opencc_backend.backend import OpenCCBackend

print("import module", round(time.perf_counter() - t, 3))
t = time.perf_counter()
b = OpenCCBackend("s2t")
print("construct s2t (cold)", round(time.perf_counter() - t, 3))
t = time.perf_counter()
r = b.self_test(include_optional=False)
print("self_test", round(time.perf_counter() - t, 3), r.passed)
t = time.perf_counter()
cfgs = b.available_configs()
print(
    "available_configs (probe jieba)", round(time.perf_counter() - t, 3), len(cfgs), b.jieba_error
)
t = time.perf_counter()
b2 = OpenCCBackend("s2twp")
print("construct s2twp (warm)", round(time.perf_counter() - t, 3))
t = time.perf_counter()
b3 = OpenCCBackend("s2twp")
print("construct s2twp again (warm)", round(time.perf_counter() - t, 3))
# throughput
from core.converter import OfficialBackendConverter
from core.models import ConvertRequest

text_nodes = [
    "这是一个用于测试转换速度的简体中文段落，其中包含软件、硬件、网络与信息等常见词汇。" * 2
] * 3000
for opts in [
    dict(detailed_classification=False, diagnose_mixed=False),
    dict(detailed_classification=True, diagnose_mixed=False),
    dict(detailed_classification=False, diagnose_mixed=True),
    dict(detailed_classification=True, diagnose_mixed=True),
]:
    conv = OfficialBackendConverter(b2)
    req = ConvertRequest("s2twp", **opts)
    t = time.perf_counter()
    for n in text_nodes:
        conv.convert(n, req)
    print("s2twp 3000 nodes", opts, round(time.perf_counter() - t, 3))
