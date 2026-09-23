"""Packaging plan §2.1/§2.3 and P-00: analyse a published Fat Plugin ZIP.

Downloads the release asset into build/review-cache/releases (skipped when
already present), then reports compressed size per payload and group, and
compares every payload's jieba_dict files (presence, CRLF, bytes).

Usage:
    .venv/bin/python docs/reviews/2026-09-23/scripts/packaging/release_zip_analysis.py [tag]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env

import json
import urllib.request
import zipfile
from collections import defaultdict

tag = sys.argv[1] if len(sys.argv) > 1 else "v0.1.0"
version = tag.removeprefix("v")
target = _env.cache_dir("releases") / f"OpenCCForSigil_{version}.zip"
if not target.exists():
    url = f"https://github.com/liyafly/OpenCCForSigil/releases/download/{tag}/{target.name}"
    urllib.request.urlretrieve(url, target)
print(f"{target.name}: {target.stat().st_size:,} bytes")

sizes: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
jieba: dict[str, dict[str, bytes]] = defaultdict(dict)
with zipfile.ZipFile(target) as archive:
    manifest = json.loads(archive.read("OpenCCForSigil/vendor/opencc/manifest.json"))
    for member in archive.infolist():
        parts = member.filename.split("/")
        if len(parts) > 4 and parts[2:4] == ["opencc", "payloads"]:
            payload = parts[4]
            relative = "/".join(parts[5:])
            group = (
                "jieba_dict"
                if "jieba_dict" in relative
                else "bin"
                if "/clib/bin/" in "/" + relative
                else "dev (static/include/cmake/pc)"
                if (
                    relative.endswith((".a", ".lib"))
                    or "/include/" in relative
                    or "/cmake/" in relative
                    or "/pkgconfig/" in relative
                )
                else "rest"
            )
            if "/jieba_dict/" in member.filename and not member.filename.endswith("/"):
                jieba[payload][parts[-1]] = archive.read(member)
        else:
            payload, group = ("plugin code" if "vendor" not in parts else "vendor other"), ""
        sizes[(payload, group)][0] += member.file_size
        sizes[(payload, group)][1] += member.compress_size
    configs = {
        name.split("/")[4]: json.loads(archive.read(name))["segmentation"]
        for name in archive.namelist()
        if name.endswith("s2twp_jieba.json")
    }

for (payload, group), (raw, zipped) in sorted(sizes.items()):
    print(f"{payload:22s} {group:32s} raw={raw / 1e6:6.2f} MB zip={zipped / 1e6:6.2f} MB")

print("\njieba_dict files per payload:")
for payload, files in sorted(jieba.items()):
    print(f"  {payload}: {sorted((name, len(data)) for name, data in files.items())}")
reference = jieba.get("macos-arm64-cp314") or next(iter(jieba.values()))
for payload, files in sorted(jieba.items()):
    for name in sorted(set(reference) | set(files)):
        mine, ref = files.get(name), reference.get(name)
        if mine == ref:
            continue
        if mine is None:
            print(f"  {payload}: MISSING {name}")
        elif ref is None:
            print(f"  {payload}: extra {name}")
        else:
            print(
                f"  {payload}: {name} differs; CRLF-only={mine.replace(b'\r\n', b'\n') == ref}; "
                f"has CRLF={b'\r\n' in mine}"
            )
print("\ns2twp_jieba segmentation config per payload:")
for payload, value in sorted(configs.items()):
    print(f"  {payload}: {value}")
print("\nmanifest payload ids:", [p["payload_path"] for p in manifest["payloads"]])
