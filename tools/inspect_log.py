#!/usr/bin/env python3
"""Minimal JSONL log inspector for development."""

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    count = 0
    with args.path.open("r", encoding="utf-8") as handle:
        for line in handle:
            json.loads(line)
            count += 1
    print(f"valid JSONL events: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
