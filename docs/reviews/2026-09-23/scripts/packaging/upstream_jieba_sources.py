"""Packaging plan §2.1, P-00, P-11: upstream loader and build rules.

Fetches the upstream OpenCC files at the commit pinned in
native_build/payload-lock.json into build/review-cache/upstream-<commit>/ and
prints the lines that decide:
- which Jieba resources are required at runtime vs. fallback-only;
- why the merged dictionary is skipped with the Visual Studio generator;
- how config/dictionary/plugin resources are searched.

Usage:
    .venv/bin/python docs/reviews/2026-09-23/scripts/packaging/upstream_jieba_sources.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env

import json
import re
import urllib.request

lock = json.loads((_env.ROOT / "native_build" / "payload-lock.json").read_text(encoding="utf-8"))
commit = lock["opencc_upstream_commit"]
cache = _env.cache_dir(f"upstream-{commit[:12]}")
FILES = {
    "plugins/jieba/src/JiebaSegmentationPlugin.cpp": (
        r"IsReadableFile\(idfPath\)|stop_words\.utf8|jieba\.dict\.utf8|user\.dict\.utf8"
        r"|FallbackToTextJiebaDictionaries|OPENCC_DATA_DIR|OPENCC_SEGMENTATION_PLUGIN_PATH"
    ),
    "plugins/jieba/CMakeLists.txt": (
        r"CMAKE_VS_PLATFORM_NAME|OPENCC_CAN_RUN_CPPJIEBA_DICT|find_program\(OPENCC_DICT"
        r"|--input|jieba_merged\.ocd2"
    ),
    "src/Config.cpp": r"OPENCC_DATA_DIR|searchPaths\.push_back|FindConfigFile",
    "python/opencc/__init__.py": r"_opencc_share_dir|CONFIGS =|resource_zip",
}
print("upstream commit:", commit)
for relative, pattern in FILES.items():
    target = cache / relative.replace("/", "__")
    if not target.exists():
        url = f"https://raw.githubusercontent.com/BYVoid/OpenCC/{commit}/{relative}"
        urllib.request.urlretrieve(url, target)
    print(f"\n===== {relative}")
    for number, line in enumerate(target.read_text(encoding="utf-8").splitlines(), 1):
        if re.search(pattern, line):
            print(f"{number:5d}: {line.rstrip()}")
