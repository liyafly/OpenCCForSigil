#!/usr/bin/env python3
"""Run the real-Qt acceptance probes for the UI workflow review."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

import PySide6
from PySide6.QtCore import qVersion


ROOT = Path(__file__).resolve().parents[5]
SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPTS = (
    ("ux01_rule_summary_regression", None),
    ("ux01_formal_tests", None),
    ("ux06_rules", ROOT / "docs/reviews/2026-09-26/scripts/check_rules_layout.py"),
    ("ux04_preview", ROOT / "docs/reviews/2026-09-27/scripts/check_preview_layout.py"),
)
LANGUAGES = ("en", "zh-Hans", "zh-Hant")
LOCALIZED_SCRIPTS = (
    ("ux02_profiles", ROOT / "docs/reviews/2026-09-26/scripts/check_profile_layout.py"),
    ("ux08_history", SCRIPT_DIR / "check_history_layout.py"),
)


def _run(name: str, command: list[str], env: dict[str, str]) -> dict:
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    entry = {
        "name": name,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "exit_code": result.returncode,
        "stdout_tail": result.stdout[-1600:],
        "stderr_tail": result.stderr[-1000:],
    }
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=640)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (
        str(ROOT / "plugin/OpenCCForSigil"), env.get("PYTHONPATH", ""))))
    reports = []
    for name, script in SCRIPTS:
        if name == "ux01_rule_summary_regression":
            target = output / name
            reports.append(_run(
                name,
                [sys.executable, str(SCRIPT_DIR / "probe_ui_workflow.py"),
                 "--output", str(target), "--verify"], env,
            ))
            continue
        if script is None:
            reports.append(_run(
                name,
                [sys.executable, "-m", "pytest", "tests/unit/test_run_options.py",
                 "tests/unit/test_profiles_m3.py", "tests/unit/test_i18n.py", "-q"],
                env,
            ))
            continue
        target = output / name
        command = [sys.executable, str(script), "--output", str(target)]
        if args.verify:
            command.append("--verify")
        command.extend(("--width", str(args.width), "--height", str(args.height)))
        reports.append(_run(name, command, env))

    for base_name, script in LOCALIZED_SCRIPTS:
        for language in LANGUAGES:
            name = f"{base_name}_{language}"
            command = [sys.executable, str(script), "--output", str(output / name),
                       "--language", language, "--width", str(args.width),
                       "--height", str(args.height)]
            if args.verify:
                command.append("--verify")
            reports.append(_run(name, command, env))

    # UX-03 uses the same merged scope/configuration entry in each UI language.
    for language in LANGUAGES:
        name = f"ux03_summary_{language}"
        command = [sys.executable, str(SCRIPT_DIR / "check_run_summary.py"),
                   "--output", str(output / name), "--language", language,
                   "--width", str(args.width), "--height", str(args.height)]
        if args.verify:
            command.append("--verify")
        reports.append(_run(name, command, env))

    history_path = output / "ux08_history_en" / "history.json"
    qt_probe = json.loads(history_path.read_text(encoding="utf-8")) \
        if history_path.exists() else {}
    report = {
        "head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                check=True, capture_output=True, text=True).stdout.strip(),
        "python": sys.version,
        "PySide6": PySide6.__version__,
        "Qt": qVersion(),
        "os": platform.platform(),
        "qpa": env.get("QT_QPA_PLATFORM", "default"),
        "logical_screen_geometry": qt_probe.get("screen_geometry"),
        "device_pixel_ratio": qt_probe.get("screen_device_pixel_ratio"),
        "requested_geometry": [args.width, args.height],
        "verify": args.verify,
        "scenarios": reports,
        "coverage": {
            "UX-01": "real Qt state and frozen-rule snapshot probe plus focused run-options/profile/i18n tests",
            "UX-02": "profile real-Qt layout at requested geometry",
            "UX-03": "merged settings summary, detail table, read-only spies, Jieba states in 3 languages",
            "UX-04": "preview commands, filters, diagnostics, and export options in 3 languages",
            "UX-05": "preview batch-decision B1/B3/B5 checks from the real-Qt preview probe",
            "UX-06": "rules real-Qt layout and editor regression checks",
            "UX-07": "saved-profile filtering/comparison real-Qt checks",
            "UX-08": "history metadata filters and stable IDs real-Qt checks",
        },
        "status": "PASS" if all(item["exit_code"] == 0 for item in reports) else "FAIL",
    }
    (output / "acceptance.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
