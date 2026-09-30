"""Shared timing allowances for CPU-bound stress tests."""

import platform
import sys


def timing_budget(seconds: float) -> float:
    """Allow more headroom on the slower Intel macOS CI runner."""

    if sys.platform == "darwin" and platform.machine() == "x86_64":
        return seconds * 1.5
    return seconds
