#!/usr/bin/env python3
"""Guarded entry point for canonical CLI golden generation."""


def main() -> int:
    print("Golden generation starts in Phase 1 and must use the pinned official CLI oracle.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
