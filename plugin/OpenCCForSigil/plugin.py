"""Thin Sigil plugin entry point.

Sigil imports this module and calls ``run(bk)``. Business logic lives in the
application controller; this file only performs bootstrap and error mapping.
"""

import sys

from app.errors import UserCancelled


def run(bk: object) -> int:
    """Run the plugin and return Sigil's integer status code."""
    try:
        from ui.qt import set_host_book
        from app.controller import Controller

        set_host_book(bk)
        return Controller(bk).run()
    except UserCancelled:
        return 1
    except Exception as exc:  # pragma: no cover - final bootstrap guard
        print(f"OpenCCForSigil failed: {exc}", file=sys.stderr)
        return 2


__all__ = ["run"]
