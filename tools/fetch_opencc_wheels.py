#!/usr/bin/env python3
"""Inspect official OpenCC wheel metadata during Build/Release.

This tool is intentionally a build-time utility. It never runs from the
plugin and never installs a package into the user's Python environment.
"""

import argparse
import json
from urllib.request import urlopen


def fetch_metadata(version: str) -> dict:
    url = f"https://pypi.org/pypi/OpenCC/{version}/json"
    with urlopen(url, timeout=30) as response:
        payload = json.load(response)
    if payload.get("info", {}).get("name", "").lower() != "opencc":
        raise RuntimeError("PyPI metadata is not the official OpenCC distribution")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="1.4.2")
    args = parser.parse_args()
    metadata = fetch_metadata(args.version)
    wheels = [
        {
            "filename": item["filename"],
            "sha256": item["digests"]["sha256"],
            "url": item["url"],
        }
        for item in metadata["urls"]
        if item["filename"].endswith(".whl")
    ]
    print(json.dumps({"version": args.version, "wheels": wheels}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
