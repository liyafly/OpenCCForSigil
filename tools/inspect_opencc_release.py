#!/usr/bin/env python3
"""Inspect pinned OpenCC release metadata without modifying vendor files."""

from fetch_opencc_wheels import fetch_metadata


def main() -> int:
    payload = fetch_metadata("1.4.2")
    print(payload["info"]["name"], payload["info"]["version"])
    print("wheel count:", sum(item["filename"].endswith(".whl") for item in payload["urls"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
