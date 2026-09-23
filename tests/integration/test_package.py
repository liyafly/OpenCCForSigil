import json
import zipfile
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tools.build_plugin import build
from tools.package_contract import package_oslist, package_runtime_ids
from tools.validate_artifact import validate as validate_artifact


def test_plugin_metadata_check_passes():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "tools/build_plugin.py", "--check"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("flavor", "runtime"),
    (("fat", None), ("platform", "macos-arm64-cp314")),
)
def test_plugin_package_is_byte_for_byte_deterministic(tmp_path, flavor, runtime):
    root = Path(__file__).resolve().parents[2]
    source_plugin_xml = root / "plugin" / "OpenCCForSigil" / "plugin.xml"
    source_manifest = root / "plugin" / "OpenCCForSigil" / "vendor" / "opencc" / "manifest.json"
    plugin_xml_before = source_plugin_xml.read_bytes()
    manifest_before = source_manifest.read_bytes()
    options = {"flavor": flavor, "runtime": runtime}
    first = build(tmp_path / "first.zip", **options)
    second = build(tmp_path / "second.zip", **options)

    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        plugin_xml = ET.fromstring(archive.read("OpenCCForSigil/plugin.xml"))
        manifest = json.loads(archive.read("OpenCCForSigil/vendor/opencc/manifest.json"))
        payloads = manifest["payloads"]
        runtimes = manifest["package"]["runtimes"]
        assert manifest["package"]["flavor"] == flavor
        assert runtimes == ([runtime] if runtime else package_runtime_ids(payloads))
        assert len(payloads) == (1 if runtime else len(runtimes))
        assert plugin_xml.findtext("oslist") == package_oslist(payloads)
    assert source_plugin_xml.read_bytes() == plugin_xml_before
    assert source_manifest.read_bytes() == manifest_before


def test_built_plugin_archive_contains_project_and_cppjieba_notices(tmp_path):
    root = Path(__file__).resolve().parents[2]
    artifact = build(tmp_path / "plugin.zip")

    with zipfile.ZipFile(artifact) as archive:
        names = set(archive.namelist())
        assert archive.read("OpenCCForSigil/LICENSE") == (root / "LICENSE").read_bytes()
        assert archive.read("OpenCCForSigil/NOTICE") == (root / "plugin" / "OpenCCForSigil" / "NOTICE").read_bytes()
        assert "OpenCCForSigil/resources/third_party/CPPJIEBA_LICENSE" in names


@pytest.mark.parametrize(
    "missing_member",
    [
        "OpenCCForSigil/LICENSE",
        "OpenCCForSigil/resources/third_party/CPPJIEBA_LICENSE",
    ],
)
def test_validator_rejects_archive_missing_required_license_file(tmp_path, missing_member):
    source = build(tmp_path / "source.zip")
    missing = tmp_path / "missing.zip"
    with zipfile.ZipFile(source) as source_archive, zipfile.ZipFile(missing, "w") as target_archive:
        for info in source_archive.infolist():
            if info.filename != missing_member:
                target_archive.writestr(info, source_archive.read(info.filename))

    with pytest.raises(SystemExit, match=missing_member):
        validate_artifact(missing)
