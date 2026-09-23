from __future__ import annotations

import json
from pathlib import Path

from tools.package_smoke import EXPECTED_CONFIGS, load_expectations


ROOT = Path(__file__).resolve().parents[2]


def test_package_smoke_expectations_cover_all_supported_configs_and_cli_inputs():
    expectations = load_expectations(ROOT / "tests" / "fixtures" / "package_smoke.jsonl")
    source_cases = {}
    for path in (
        ROOT / "tests" / "fixtures" / "opencc_smoke.jsonl",
        ROOT / "tests" / "fixtures" / "opencc_jieba_smoke.jsonl",
    ):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                case = json.loads(line)
                source_cases.setdefault(case["config"], set()).add(case["source"])

    assert {case["config"] for case in expectations} == EXPECTED_CONFIGS
    assert len(expectations) == len(EXPECTED_CONFIGS)
    assert all(case["source"] in source_cases[case["config"]] for case in expectations)


def test_package_smoke_rejects_missing_config_expectation(tmp_path: Path):
    path = tmp_path / "incomplete.jsonl"
    path.write_text(
        '{"id":"only-s2t","config":"s2t","source":"汉字","expected":"漢字"}\n',
        encoding="utf-8",
    )

    try:
        load_expectations(path)
    except SystemExit as exc:
        assert "every supported config once" in str(exc)
    else:
        raise AssertionError("incomplete package smoke expectations were accepted")
