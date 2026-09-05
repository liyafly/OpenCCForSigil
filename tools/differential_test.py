#!/usr/bin/env python3
"""Guarded entry point for official CLI vs Python Binding differential tests."""


def main() -> int:
    print("Differential testing starts in Phase 1; no self-generated oracle is accepted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
