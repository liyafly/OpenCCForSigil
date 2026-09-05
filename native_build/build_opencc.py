#!/usr/bin/env python3
"""Compatibility entry point for the official wheel vendor pipeline."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from vendor_opencc import main  # noqa: E402


if __name__ == "__main__":
    main()
