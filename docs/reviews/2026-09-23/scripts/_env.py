"""Shared bootstrap for the 2026-09-23 review scripts.

Import this first (after putting this directory on ``sys.path``). It makes the
scripts runnable from any working directory:

- the plugin package, the repository root and ``tests/unit`` become importable;
- the working directory becomes the repository root, so relative paths such as
  ``plugin/OpenCCForSigil`` behave as they do in the test suite;
- downloads go to ``build/review-cache`` (git-ignored), never into the tree.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PLUGIN = ROOT / "plugin" / "OpenCCForSigil"
CACHE = ROOT / "build" / "review-cache"

sys.path[:0] = [str(PLUGIN), str(ROOT), str(ROOT / "tests" / "unit")]
os.chdir(ROOT)


def cache_dir(*parts: str) -> Path:
    """Return a git-ignored download directory, creating it if needed."""

    path = CACHE.joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path
