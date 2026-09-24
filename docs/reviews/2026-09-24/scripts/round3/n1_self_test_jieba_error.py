"""N-01: self_test raises AttributeError when the optional Jieba probe fails.

Expect after the fix: checks["config"] and checks["s2t_smoke"] are True and the
error text names the Jieba failure, not '_jieba_error'.
"""

import tempfile
from pathlib import Path

import common  # noqa: F401
from test_optional_jieba import backend_with_loader

backend, _loader = backend_with_loader(Path(tempfile.mkdtemp()))
result = backend.self_test()
print("passed:", result.passed)
print("error:", result.error)
print("config:", result.checks.get("config"), "s2t_smoke:", result.checks.get("s2t_smoke"))
