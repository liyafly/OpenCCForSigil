#!/usr/bin/env python3
"""Compare official native Jieba configs through Python Binding and CLI."""

from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
JIEBA_CONFIGS = {
    "s2t_jieba",
    "s2tw_jieba",
    "s2twp_jieba",
    "s2hk_jieba",
    "s2hkp_jieba",
    "tw2sp_jieba",
    "hk2sp_jieba",
}


def load_cases(path: Path) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            value = json.loads(line)
        except ValueError as exc:
            raise SystemExit(f"invalid JSONL at {path}:{line_number}") from exc
        if not isinstance(value, dict):
            raise SystemExit(f"corpus case must be an object at {path}:{line_number}")
        missing = [key for key in ("id", "config", "source") if not isinstance(value.get(key), str)]
        if missing:
            raise SystemExit(f"corpus case missing string fields at {path}:{line_number}: {missing}")
        if value["config"] not in JIEBA_CONFIGS:
            raise SystemExit(
                f"corpus uses unsupported official Jieba config at {path}:{line_number}: "
                f"{value['config']}"
            )
        cases.append({"id": value["id"], "config": value["config"], "source": value["source"]})
    if not cases:
        raise SystemExit(f"corpus is empty: {path}")
    return cases


def _configure_plugin_environment(payload_root: Path) -> Path:
    data_root = payload_root / "opencc" / "clib" / "share" / "opencc"
    if not data_root.is_dir():
        raise SystemExit(f"OpenCC data directory is missing: {data_root}")
    plugin_candidates = sorted(
        path.parent
        for path in payload_root.rglob("*")
        if path.is_file()
        and "opencc-jieba" in path.name.lower()
        and path.suffix.lower() in {".dll", ".dylib", ".so"}
    )
    if len(plugin_candidates) != 1:
        raise SystemExit(
            "expected exactly one vendored official opencc-jieba library, found: "
            + ", ".join(str(path) for path in plugin_candidates)
        )
    os.environ["OPENCC_DATA_DIR"] = str(data_root)
    os.environ["OPENCC_SEGMENTATION_PLUGIN_PATH"] = str(plugin_candidates[0])
    return data_root


def _resolve_payload(payload_root: Path | None) -> Path:
    if payload_root is not None:
        return payload_root.resolve()
    sys.path.insert(0, str(ROOT / "plugin" / "OpenCCForSigil"))
    from opencc_backend.runtime_selector import RuntimeSelector

    _, _, root = RuntimeSelector().select()
    return root


def run_cli(cli: Path, config: str, source: str, config_root: Path) -> str:
    config_path = config_root / f"{config}.json"
    if not config_path.is_file():
        raise RuntimeError(f"official Jieba config is missing: {config_path}")
    result = subprocess.run(
        [str(cli), "--include-tofu-risk-dictionaries", "-c", str(config_path)],
        input=source.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_cli_environment(config_root.parents[3]),
        check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"official OpenCC CLI failed for {config}: {detail}")
    return result.stdout.decode("utf-8")


def _cli_environment(payload_root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    runtime_dirs = (
        payload_root / "opencc.libs",
        payload_root / "opencc" / "clib" / "bin",
    )
    existing = environment.get("PATH", "")
    environment["PATH"] = os.pathsep.join(
        [str(path) for path in runtime_dirs if path.is_dir()] + [existing]
    )
    return environment


def run_python_binding(payload_root: Path, cases: Iterable[Mapping[str, str]]) -> list[str]:
    payload_root = payload_root.resolve()
    _configure_plugin_environment(payload_root)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(payload_root))
    module = importlib.import_module("opencc")
    origin = Path(str(module.__file__)).resolve()
    if payload_root not in origin.parents:
        raise RuntimeError(f"Python Binding imported outside selected payload: {origin}")
    converters: dict[str, Any] = {}
    outputs: list[str] = []
    for case in cases:
        config = case["config"]
        converter = converters.setdefault(config, module.OpenCC(config))
        outputs.append(converter.convert(case["source"]))
    return outputs


def compare(cli: Path, payload_root: Path, cases: list[dict[str, str]]) -> list[dict[str, object]]:
    config_root = _configure_plugin_environment(payload_root)
    python_outputs = run_python_binding(payload_root, cases)
    differences: list[dict[str, object]] = []
    for case, python_output in zip(cases, python_outputs, strict=True):
        cli_output = run_cli(cli, case["config"], case["source"], config_root)
        if python_output != cli_output:
            differences.append(
                {
                    "id": case["id"],
                    "config": case["config"],
                    "python_output": python_output,
                    "cli_output": cli_output,
                }
            )
    return differences


def _default_cli(payload_root: Path) -> Path:
    bin_root = payload_root / "opencc" / "clib" / "bin"
    windows_cli = bin_root / "opencc.exe"
    return windows_cli if windows_cli.is_file() else bin_root / "opencc"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", type=Path, help="matching official OpenCC CLI executable")
    parser.add_argument("--corpus", type=Path, required=True, help="source-only Jieba JSONL corpus")
    parser.add_argument("--payload-root", type=Path, help="exact vendored payload")
    args = parser.parse_args()
    cases = load_cases(args.corpus)
    payload_root = _resolve_payload(args.payload_root)
    cli = args.cli or _default_cli(payload_root)
    if not cli.is_file():
        raise SystemExit(f"official CLI is missing: {cli}")
    differences = compare(cli, payload_root, cases)
    if differences:
        print(
            json.dumps(
                {"status": "blocking-difference", "differences": differences},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    print(
        "official native Jieba CLI/Python Binding differential test passed "
        f"({len(cases)} cases; 100% equality)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
