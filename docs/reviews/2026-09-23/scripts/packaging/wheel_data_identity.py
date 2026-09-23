"""Packaging plan §2.2/§2.4: official OpenCC wheels on PyPI.

Downloads the pinned-version cp314 wheels into build/review-cache/wheels,
verifies each sha256 against PyPI, then reports:
- which platforms have a cp314 wheel (and whether any release has win_arm64);
- whether share/opencc data is byte-identical across wheels, and whether any
  difference is CRLF-only / JSON-equivalent;
- per-wheel size by group, and the DLL names the Windows .pyd imports.

Usage:
    .venv/bin/python docs/reviews/2026-09-23/scripts/packaging/wheel_data_identity.py [version]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _env

import hashlib
import json
import re
import urllib.request
import zipfile

version = sys.argv[1] if len(sys.argv) > 1 else "1.4.2"
cache = _env.cache_dir("wheels")


def fetch_json(url: str, name: str) -> dict:
    target = cache / name
    if not target.exists():
        urllib.request.urlretrieve(url, target)
    return json.loads(target.read_text(encoding="utf-8"))


release = fetch_json(f"https://pypi.org/pypi/OpenCC/{version}/json", f"opencc-{version}.json")
project = fetch_json("https://pypi.org/pypi/OpenCC/json", "opencc-project.json")
print("latest on PyPI:", project["info"]["version"])
print(
    "releases with any win_arm64 wheel:",
    [
        v
        for v, files in project["releases"].items()
        if any("win_arm64" in f["filename"] for f in files)
    ],
)

wheels = [u for u in release["urls"] if "-cp314-" in u["filename"]]
tables: dict[str, dict[str, bytes]] = {}
for info in wheels:
    path = cache / info["filename"]
    if not path.exists():
        urllib.request.urlretrieve(info["url"], path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != info["digests"]["sha256"]:
        raise SystemExit(f"sha256 mismatch for {path.name}")
    platform = info["filename"].split("-cp314-")[1]
    with zipfile.ZipFile(path) as archive:
        tables[platform] = {
            name.split("/share/opencc/", 1)[1]: archive.read(name)
            for name in archive.namelist()
            if "/share/opencc/" in name and not name.endswith("/")
        }
        groups: dict[str, list[float]] = {}
        for member in archive.infolist():
            name = member.filename
            group = (
                "bin"
                if "/clib/bin/" in name
                else "static/headers/cmake/pc"
                if (
                    name.endswith((".a", ".lib"))
                    or "/include/" in name
                    or "/cmake/" in name
                    or "/pkgconfig/" in name
                )
                else "native"
                if name.endswith((".so", ".pyd", ".dll", ".dylib"))
                else "data"
                if "/share/" in name
                else "other"
            )
            entry = groups.setdefault(group, [0.0, 0.0])
            entry[0] += member.file_size / 1e6
            entry[1] += member.compress_size / 1e6
        print(platform, {k: (round(v[0], 2), round(v[1], 2)) for k, v in groups.items()})
        if "win_amd64" in platform:
            pyd = next(n for n in archive.namelist() if n.endswith(".pyd"))
            names = sorted(
                {
                    m.decode("ascii", "ignore")
                    for m in re.findall(rb"[A-Za-z0-9_\-.]+\.dll", archive.read(pyd))
                }
            )
            print("  DLL names referenced by the Windows pyd:", names)
    if "aarch64" in platform:
        print(
            "  aarch64 pin:", info["filename"], info["size"], info["digests"]["sha256"], info["url"]
        )

names = list(tables)
base_name = next(name for name in names if "win" not in name)
base = tables[base_name]
print(f"share/opencc files in {base_name}: {len(base)}")
for name in names:
    if name == base_name:
        continue
    other = tables[name]
    differing = sorted(k for k in set(base) | set(other) if base.get(k) != other.get(k))
    crlf_only = all(
        k in base and k in other and other[k].replace(b"\r\n", b"\n") == base[k] for k in differing
    )
    json_equal = all(
        json.loads(other[k]) == json.loads(base[k])
        for k in differing
        if k.endswith(".json") and k in base and k in other
    )
    ocd2 = [k for k in differing if k.endswith(".ocd2")]
    print(
        f"{name}: {len(differing)} differing files; ocd2 differing={ocd2}; "
        f"CRLF-only={crlf_only}; JSON-equal={json_equal}"
    )
