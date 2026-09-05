#!/usr/bin/env python3
"""Inspect official OpenCC wheel metadata during Build/Release.

This tool is intentionally a build-time utility. It never runs from the
plugin and never installs a package into the user's Python environment.
"""

import argparse
from http.client import IncompleteRead
import json
from time import sleep
from urllib.error import URLError
from urllib.request import Request, urlopen


_USER_AGENT = "OpenCCForSigil-build/0.1 (+official-wheel-vendor)"


def fetch_metadata(version: str) -> dict:
    url = f"https://pypi.org/pypi/OpenCC/{version}/json"
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            request = Request(url, headers={"User-Agent": _USER_AGENT})
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except (IncompleteRead, OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt == 3:
                raise RuntimeError(f"could not fetch PyPI metadata for OpenCC {version}") from exc
            sleep(1 << attempt)
    else:  # pragma: no cover - the loop either breaks or raises
        raise RuntimeError("unreachable metadata fetch state") from last_error
    if payload.get("info", {}).get("name", "").lower() != "opencc":
        raise RuntimeError("PyPI metadata is not the official OpenCC distribution")
    if payload.get("info", {}).get("version") != version:
        raise RuntimeError(
            f"PyPI returned OpenCC {payload.get('info', {}).get('version')!r}, expected {version!r}"
        )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="1.4.2")
    args = parser.parse_args()
    metadata = fetch_metadata(args.version)
    wheels = [
        {
            "filename": item["filename"],
            "size": item.get("size"),
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
