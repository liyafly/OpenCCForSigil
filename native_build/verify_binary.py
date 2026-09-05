#!/usr/bin/env python3
"""Verify one extracted official OpenCC payload without importing user packages."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin" / "OpenCCForSigil"))

from opencc_backend.integrity import verify_tree_sha256  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", type=Path)
    parser.add_argument("--sha256", required=True, help="expected deterministic payload tree SHA-256")
    args = parser.parse_args()
    actual = verify_tree_sha256(args.payload.resolve(), args.sha256)
    print(f"payload verified: {args.payload} ({actual})")
    return 0


if __name__ == "__main__":
    main()
