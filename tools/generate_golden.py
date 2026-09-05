#!/usr/bin/env python3
"""Generate reviewable golden candidates from the independent official CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from differential_test import load_cases, run_cli


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", type=Path, required=True, help="independent official OpenCC CLI executable")
    parser.add_argument("--corpus", type=Path, required=True, help="source-only JSONL corpus")
    parser.add_argument(
        "--config-root",
        type=Path,
        help="directory containing pinned JSON configs; defaults to the CLI payload's share/opencc directory",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--force",
        action="store_true",
        help="explicitly replace an existing candidate file; human review is still required",
    )
    args = parser.parse_args()
    if not args.cli.is_file():
        raise SystemExit(f"official CLI is missing: {args.cli}")
    if args.output.exists() and not args.force:
        raise SystemExit(f"refusing to overwrite existing golden file without --force: {args.output}")
    cases = load_cases(args.corpus)
    config_root = args.config_root
    if config_root is None:
        config_root = args.cli.resolve().parent.parent / "share" / "opencc"
    if not config_root.is_dir():
        raise SystemExit(f"official OpenCC config directory is missing: {config_root}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for case in cases:
            expected = run_cli(args.cli, case["config"], case["source"], config_root)
            handle.write(
                json.dumps(
                    {**case, "expected": expected},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )
    print(f"generated {len(cases)} CLI golden candidates at {args.output}; human review is required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
