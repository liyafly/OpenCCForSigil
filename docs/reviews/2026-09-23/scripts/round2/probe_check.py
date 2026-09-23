import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env  # noqa: F401  (repo import paths, cwd = repo root)
import time

from opencc_backend.backend import OpenCCBackend

b = OpenCCBackend("s2t")
t = time.perf_counter()
b.start_jieba_probe()
print("start", time.perf_counter() - t)
print("state0", b.jieba_probe_state()[0])
print(
    "nonblocking has jieba?", any(c.endswith("_jieba") for c in b.available_configs_nonblocking())
)
b._jieba_future.result()
print("state1", b.jieba_probe_state())
print("jieba in available", [c for c in b.available_configs() if c.endswith("_jieba")])
b2 = OpenCCBackend("s2t_jieba")
print("new backend state", b2.jieba_probe_state()[0])
