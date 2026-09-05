"""Thin Sigil plugin entry point.

Sigil imports this module and calls ``run(bk)``. Business logic lives in the
application controller; this file only performs bootstrap and error mapping.
"""

import sys

from app.errors import UserCancelled
from app.version import (
    PRODUCTION_PYTHON_BASELINE,
    SUPPORTED_PYTHON_IMPLEMENTATION,
    SUPPORTED_PYTHON_MAJOR,
    SUPPORTED_PYTHON_MINOR,
    supports_formal_runtime,
)


def run(bk: object) -> int:
    """Run the plugin and return Sigil's integer status code."""

    if not supports_formal_runtime(sys.implementation.name, sys.version_info):
        print(
            "OpenCCForSigil V1 requires "
            f"{SUPPORTED_PYTHON_IMPLEMENTATION} {SUPPORTED_PYTHON_MAJOR}."
            f"{SUPPORTED_PYTHON_MINOR}.x; production baseline is Sigil bundled "
            f"Python {PRODUCTION_PYTHON_BASELINE}",
            file=sys.stderr,
        )
        return 2

    try:
        from app.controller import Controller

        return Controller(bk).run()
    except UserCancelled:
        return 1
    except Exception as exc:  # pragma: no cover - final bootstrap guard
        print(f"OpenCCForSigil failed: {exc}", file=sys.stderr)
        return 2


__all__ = ["run"]
