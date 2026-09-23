"""Packaging plan §2.1: compressed size of each group in a local payload.

Usage (repo root or anywhere):
    .venv/bin/python docs/reviews/2026-09-23/scripts/packaging/payload_sizes.py [payload-id]

Default payload id: macos-arm64-cp314 (the one checked into the repository).
Each file is deflated on its own at level 9, matching tools/build_plugin.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env

import io
import zipfile


def deflated_size(data: bytes) -> int:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr("x", data)
    return len(buffer.getvalue())


def group_of(relative: str) -> str:
    if "/jieba_dict/" in relative:
        return "jieba_dict (data)"
    if relative.startswith("opencc/clib/bin/"):
        return "bin (CLI tools)"
    if (
        relative.endswith((".a", ".lib"))
        or "/include/" in relative
        or "/cmake/" in relative
        or "/pkgconfig/" in relative
    ):
        return "static libs/headers/cmake/pkgconfig"
    if relative.endswith((".so", ".dylib", ".pyd", ".dll")):
        return "native runtime libs"
    if "/share/opencc/" in relative:
        return "standard dicts+configs"
    return "python/dist-info/other"


payload_id = sys.argv[1] if len(sys.argv) > 1 else "macos-arm64-cp314"
root = _env.PLUGIN / "vendor" / "opencc" / "payloads" / payload_id
if not root.is_dir():
    raise SystemExit(f"payload not found: {root}")

groups: dict[str, list[int]] = {}
jieba: list[tuple[str, int, int]] = []
for path in sorted(p for p in root.rglob("*") if p.is_file()):
    relative = path.relative_to(root).as_posix()
    data = path.read_bytes()
    zipped = deflated_size(data)
    entry = groups.setdefault(group_of(relative), [0, 0, 0])
    entry[0] += len(data)
    entry[1] += zipped
    entry[2] += 1
    if "/jieba_dict/" in relative:
        jieba.append((path.name, len(data), zipped))

total_raw = sum(value[0] for value in groups.values())
total_zip = sum(value[1] for value in groups.values())
print(f"payload {payload_id}")
for name, (raw, zipped, count) in sorted(groups.items(), key=lambda item: -item[1][0]):
    print(f"  {name:38s} files={count:3d} raw={raw / 1e6:6.2f} MB zip={zipped / 1e6:6.2f} MB")
print(f"  {'TOTAL':38s}           raw={total_raw / 1e6:6.2f} MB zip={total_zip / 1e6:6.2f} MB")
print("jieba_dict files:")
for name, raw, zipped in jieba:
    print(f"  {name:22s} raw={raw / 1e6:5.2f} MB zip={zipped / 1e6:5.2f} MB")
