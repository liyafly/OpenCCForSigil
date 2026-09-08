from __future__ import annotations

from pathlib import Path
import zipfile

import pytest

from tools.build_plugin import build
from tools.validate_artifact import validate as validate_artifact


ROOT = Path(__file__).resolve().parents[2]
NOTICE_ROOT = ROOT / "plugin" / "OpenCCForSigil" / "resources" / "third_party"


@pytest.fixture(scope="module")
def artifact(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build(tmp_path_factory.mktemp("notice-artifact") / "plugin.zip")


def _without_member(source: Path, target: Path, missing: str) -> None:
    with zipfile.ZipFile(source) as source_archive, zipfile.ZipFile(target, "w") as target_archive:
        for info in source_archive.infolist():
            if info.filename != missing:
                target_archive.writestr(info, source_archive.read(info.filename))


@pytest.mark.parametrize(
    "notice",
    [
        "MARISA_COPYING.md",
        "DARTS_CLONE_COPYING.md",
        "RAPIDJSON_LICENSE.txt",
        "TCLAP_COPYING",
        "PYBIND11_LICENSE",
        "CPPJIEBA_LICENSE",
    ],
)
def test_validator_requires_each_shipped_dependency_notice(
    artifact: Path, tmp_path: Path, notice: str
):
    member = f"OpenCCForSigil/resources/third_party/{notice}"
    target = tmp_path / f"missing-{notice.replace('/', '-')}.zip"
    _without_member(artifact, target, member)

    with pytest.raises(SystemExit, match=notice.replace(".", r"\.")):
        validate_artifact(target)


def test_dependency_index_records_pinned_inputs_and_unshipped_test_dependencies():
    index = (NOTICE_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    for component in (
        "marisa-trie 0.3.1",
        "darts-clone 0.32h",
        "rapidjson 1.1.0",
        "tclap 1.2.5",
        "pybind11 2.13.1",
        "cppjieba",
    ):
        assert component in index
    assert "025f371dc76b598d77384fbdab90c937471844d8" in index
    assert "Google Test and Google Benchmark" in index
    assert "not present in the shipped payloads" in index


def test_dependency_notice_text_preserves_license_and_attribution_markers():
    expected_markers = {
        "MARISA_COPYING.md": ("BSD-2-Clause OR LGPL-2.1-or-later", "Susumu Yata"),
        "DARTS_CLONE_COPYING.md": ("BSD 2-clause license", "Susumu Yata"),
        "RAPIDJSON_LICENSE.txt": ("RapidJSON", "THL A29 Limited"),
        "TCLAP_COPYING": ("Michael E. Smoot", "Google Inc."),
        "PYBIND11_LICENSE": ("Wenzel Jakob", "Redistribution and use"),
        "CPPJIEBA_LICENSE": ("The MIT License", "Copyright"),
    }
    for filename, markers in expected_markers.items():
        text = (NOTICE_ROOT / filename).read_text(encoding="utf-8")
        assert all(marker in text for marker in markers), filename
