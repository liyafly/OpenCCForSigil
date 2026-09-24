#!/usr/bin/env python3
"""Compare native Jieba conversion results emitted by CI platform runners."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping, Sequence


EXPECTED_PLATFORMS = frozenset({
    "linux-aarch64",
    "linux-x86_64",
    "macos-arm64",
    "macos-x86_64",
    "windows-x86_64",
})


def _output_map(
    platform: str,
    records: Sequence[Mapping[str, object]],
) -> dict[tuple[str, str], str]:
    results = {}
    for index, record in enumerate(records):
        config = record.get("config")
        source = record.get("input")
        output = record.get("output")
        if not all(isinstance(value, str) for value in (config, source, output)):
            raise ValueError(
                f"malformed Jieba output record {index} for {platform}: "
                "config, input, and output must be strings"
            )
        key = (config, source)
        if key in results:
            raise ValueError(
                f"duplicate Jieba output record for {platform}: config={config}, input={source!r}"
            )
        results[key] = output
    return results


def first_difference(
    platform_outputs: Mapping[str, Sequence[Mapping[str, object]]],
) -> dict[str, str] | None:
    """Return the first cross-platform mismatch, or None when outputs match."""

    platforms = sorted(platform_outputs)
    if len(platforms) < 2:
        raise ValueError("at least two platform outputs are required")
    normalized = {
        platform: _output_map(platform, platform_outputs[platform])
        for platform in platforms
    }
    reference_platform = platforms[0]
    reference = normalized[reference_platform]
    for platform in platforms[1:]:
        candidate = normalized[platform]
        for config, source in sorted(
                set(reference) | set(candidate), key=lambda item: (item[1], item[0])):
            reference_output = reference.get((config, source))
            platform_output = candidate.get((config, source))
            if reference_output != platform_output:
                return {
                    "reference_platform": reference_platform,
                    "platform": platform,
                    "config": config,
                    "input": source,
                    "reference_output": (
                        reference_output if reference_output is not None else "<missing>"),
                    "platform_output": (
                        platform_output if platform_output is not None else "<missing>"),
                }
    return None


def read_output_json(path: Path, platform: str) -> list[dict[str, str]]:
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"could not read Jieba output artifact {path}: {exc}") from exc
    if not isinstance(records, list) or not records:
        raise ValueError(f"Jieba output artifact must contain a non-empty JSON array: {path}")
    if any(not isinstance(record, dict) for record in records):
        raise ValueError(f"Jieba output artifact contains a non-object record: {path}")
    _output_map(platform, records)
    return records


def compare_json_files(platform_paths: Mapping[str, Path]) -> dict[str, str] | None:
    outputs = {
        platform: read_output_json(path, platform)
        for platform, path in platform_paths.items()
    }
    return first_difference(outputs)


def load_artifacts(input_dir: Path) -> dict[str, list[dict[str, str]]]:
    outputs = {}
    for path in sorted(input_dir.glob("jieba-outputs-*/*.json")):
        platform = path.parent.name.removeprefix("jieba-outputs-")
        if platform in outputs:
            raise ValueError(f"multiple Jieba output files found for {platform}")
        outputs[platform] = read_output_json(path, platform)

    found = set(outputs)
    missing = sorted(EXPECTED_PLATFORMS - found)
    unexpected = sorted(found - EXPECTED_PLATFORMS)
    if missing or unexpected:
        details = []
        if missing:
            details.append("missing platforms=" + ",".join(missing))
        if unexpected:
            details.append("unexpected platforms=" + ",".join(unexpected))
        raise ValueError("Jieba output artifact matrix mismatch: " + "; ".join(details))
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        outputs = load_artifacts(args.input_dir)
        difference = first_difference(outputs)
    except (OSError, ValueError) as exc:
        print(f"Jieba consistency check failed: {exc}")
        return 1
    if difference is not None:
        print("first cross-platform Jieba output mismatch:")
        print(json.dumps(difference, ensure_ascii=False, indent=2))
        return 1
    case_count = len(next(iter(outputs.values())))
    print(
        "native Jieba outputs match across "
        f"{len(outputs)} platforms ({case_count} cases per platform)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
