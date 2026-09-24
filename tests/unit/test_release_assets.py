from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib
import zipfile
import xml.etree.ElementTree as ET

import pytest

from app.version import PLUGIN_VERSION
from tools.build_plugin import validate as validate_plugin
from tools.release_assets import (
    expected_zip_names,
    validate_plugin_zip_version,
    validate_release_assets,
    write_checksums,
)
from tools.package_contract import package_asset_name


ROOT = Path(__file__).resolve().parents[2]


def test_current_plugin_metadata_and_project_versions_are_consistent():
    plugin_xml = ET.parse(ROOT / "plugin" / "OpenCCForSigil" / "plugin.xml").getroot()
    assert plugin_xml.findtext("version") == PLUGIN_VERSION
    assert plugin_xml.findtext("author") == "liyafly"

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == PLUGIN_VERSION

    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    project = next(
        package for package in lock["package"] if package["name"] == "opencc-for-sigil"
    )
    assert project["version"] == PLUGIN_VERSION
    assert validate_plugin() == PLUGIN_VERSION


def _extract_run_block(workflow: str, step_name: str) -> str:
    """Extract one literal YAML ``run: |`` block for local contract testing."""

    marker = f"      - name: {step_name}\n"
    step = workflow.split(marker, maxsplit=1)[1]
    run_marker = "        run: |\n"
    body = step.split(run_marker, maxsplit=1)[1]
    lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("          "):
            lines.append(line[10:])
        elif not line.strip():
            lines.append("")
        else:
            break
    return "\n".join(lines)


def test_ci_and_release_contract_smokes_each_package_and_publishes_eight_assets():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    release_job = workflow.split("  publish-release:", maxsplit=1)[1]
    release_shell = _extract_run_block(release_job, "Create GitHub release")

    assert "build_spec_bundle.py" not in workflow
    assert "OpenCCForSigil_Spec_v1.4_bundle.zip" not in workflow
    assert "spec_zip" not in release_job
    assert "spec-bundle" not in (ROOT / "Makefile").read_text(encoding="utf-8")
    assert not (ROOT / "tools" / "build_spec_bundle.py").exists()
    assert "  build-packages:" in workflow
    assert "  package-smoke:" in workflow
    assert "needs: build-packages" in workflow.split("  package-smoke:", maxsplit=1)[1]
    assert "    needs:\n      - package-smoke\n      - attest-release-assets" in release_job
    assert "OpenCCForSigil-packages-${{ github.sha }}" in workflow
    assert "tools/package_smoke.py" in workflow
    assert "      - name: Smoke-test the Fat Plugin under CPython 3.14\n        shell: bash" in workflow
    assert "tools/release_assets.py" in workflow
    assert release_shell.count("gh release create") == 1
    assert '"release-artifacts/OpenCCForSigil_${version}.zip"' in release_shell
    assert '"release-artifacts/OpenCCForSigil_${version}_macos-arm64.zip"' in release_shell
    assert '"release-artifacts/OpenCCForSigil_${version}_macos-x86_64.zip"' in release_shell
    assert '"release-artifacts/OpenCCForSigil_${version}_windows-x86_64.zip"' in release_shell
    assert '"release-artifacts/OpenCCForSigil_${version}_linux-x86_64.zip"' in release_shell
    assert '"release-artifacts/OpenCCForSigil_${version}_linux-aarch64.zip"' in release_shell
    assert '"release-artifacts/OpenCCForSigil_${version}_linux-x86_64-cp312.zip"' in release_shell
    assert '"release-artifacts/SHA256SUMS.txt"' in release_shell


def test_release_ci_pins_actions_and_attests_all_published_assets():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    attest_job = workflow.split("  attest-release-assets:", maxsplit=1)[1].split(
        "  package-smoke:", maxsplit=1
    )[0]
    release_job = workflow.split("  publish-release:", maxsplit=1)[1]
    verify_shell = _extract_run_block(release_job, "Verify release asset attestations")
    action_refs = [
        line.strip().split("uses:", maxsplit=1)[1].split("#", maxsplit=1)[0].strip()
        for line in workflow.splitlines()
        if "uses:" in line
    ]

    assert action_refs
    assert all("@" in reference and len(reference.rsplit("@", maxsplit=1)[1]) == 40
               for reference in action_refs)
    assert "attestations: write" in attest_job
    assert "id-token: write" in attest_job
    assert "artifact-metadata: write" in attest_job
    assert "uses: actions/attest@" in attest_job
    assert "subject-path: release-artifacts/*" in attest_job
    assert "attest-release-assets" in release_job.split("runs-on:", maxsplit=1)[0]
    assert "attestations: read" in release_job
    assert "GH_TOKEN: ${{ github.token }}" in release_job
    assert 'gh attestation verify "$asset"' in verify_shell
    assert '--repo "$GH_REPO"' in verify_shell
    assert '--signer-workflow "$GH_REPO/.github/workflows/ci.yml"' in verify_shell
    assert "release-artifacts/*.zip" in verify_shell
    assert "release-artifacts/SHA256SUMS.txt" in verify_shell


def test_expected_release_zip_names_cover_fat_and_six_platforms():
    names = expected_zip_names(PLUGIN_VERSION)
    assert len(names) == 7
    assert names["fat"] == f"OpenCCForSigil_{PLUGIN_VERSION}.zip"
    assert set(names.values()) == {
        f"OpenCCForSigil_{PLUGIN_VERSION}.zip",
        f"OpenCCForSigil_{PLUGIN_VERSION}_macos-arm64.zip",
        f"OpenCCForSigil_{PLUGIN_VERSION}_macos-x86_64.zip",
        f"OpenCCForSigil_{PLUGIN_VERSION}_windows-x86_64.zip",
        f"OpenCCForSigil_{PLUGIN_VERSION}_linux-x86_64.zip",
        f"OpenCCForSigil_{PLUGIN_VERSION}_linux-aarch64.zip",
        f"OpenCCForSigil_{PLUGIN_VERSION}_linux-x86_64-cp312.zip",
    }


def test_cp312_platform_asset_keeps_abi_in_filename():
    assert package_asset_name("0.2.0", "platform", "linux-x86_64-cp312") == (
        "OpenCCForSigil_0.2.0_linux-x86_64-cp312.zip"
    )


def test_release_asset_zip_version_must_match_the_tag(tmp_path: Path):
    archive_path = tmp_path / "OpenCCForSigil_0.1.0.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "OpenCCForSigil/plugin.xml",
            '<plugin><version>0.1.1</version></plugin>',
        )

    with pytest.raises(SystemExit, match="does not match release version"):
        validate_plugin_zip_version(archive_path, "0.1.0")


def test_release_asset_set_checksums_and_package_contracts(tmp_path: Path):
    version = "0.1.0"
    names = expected_zip_names(version)
    records = [
        ("linux-aarch64-cp314", "linux", "aarch64"),
        ("linux-x86_64-cp314", "linux", "x86_64"),
        ("linux-x86_64-cp312", "linux", "x86_64"),
        ("macos-arm64-cp314", "macos", "arm64"),
        ("macos-x86_64-cp314", "macos", "x86_64"),
        ("windows-x86_64-cp314", "windows", "x86_64"),
    ]

    for runtime, filename in names.items():
        selected = (
            [record for record in records if record[0].endswith("cp314")]
            if runtime == "fat"
            else [record for record in records if record[0] == runtime]
        )
        payloads = [
            {
                "payload_path": f"payloads/{payload_id}",
                "os": os_name,
                "architecture": architecture,
            }
            for payload_id, os_name, architecture in selected
        ]
        flavor = "fat" if runtime == "fat" else "platform"
        package = {"flavor": flavor, "runtimes": sorted(item["payload_path"][9:] for item in payloads),
                   "asset_name": filename}
        oslist = "osx,unx,win" if flavor == "fat" else {
            "macos": "osx", "linux": "unx", "windows": "win",
        }[payloads[0]["os"]]
        manifest = {"package": package, "payloads": payloads}
        archive_path = tmp_path / filename
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr(
                "OpenCCForSigil/plugin.xml",
                f"<plugin><version>{version}</version><oslist>{oslist}</oslist></plugin>",
            )
            archive.writestr(
                "OpenCCForSigil/vendor/opencc/manifest.json",
                json.dumps(manifest),
            )

    write_checksums(tmp_path, version)
    validate_release_assets(tmp_path, version)
    (tmp_path / "SHA256SUMS.txt").write_text("tampered\n", encoding="ascii")
    with pytest.raises(SystemExit, match="invalid or duplicate checksum line"):
        validate_release_assets(tmp_path, version)


@pytest.mark.parametrize(
    ("version", "release_flags", "has_notes"),
    [
        ("0.0.3-beta", ["--prerelease", "--latest=false"], False),
        ("0.1.0", ["--latest"], True),
        ("0.1.1", ["--latest"], False),
    ],
)
def test_extracted_release_shell_uploads_the_version_named_zip_with_mock_gh(
    tmp_path, version, release_flags, has_notes
):
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is required to execute the workflow's shell block")

    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    release_job = workflow.split("  publish-release:", maxsplit=1)[1]
    release_shell = _extract_run_block(release_job, "Create GitHub release")

    release_artifacts = tmp_path / "release-artifacts"
    release_artifacts.mkdir()
    assets = [
        f"OpenCCForSigil_{version}.zip",
        f"OpenCCForSigil_{version}_macos-arm64.zip",
        f"OpenCCForSigil_{version}_macos-x86_64.zip",
        f"OpenCCForSigil_{version}_windows-x86_64.zip",
        f"OpenCCForSigil_{version}_linux-x86_64.zip",
        f"OpenCCForSigil_{version}_linux-x86_64-cp312.zip",
        f"OpenCCForSigil_{version}_linux-aarch64.zip",
        "SHA256SUMS.txt",
    ]
    for asset in assets:
        (release_artifacts / asset).write_bytes(b"release artifact")
    notes_path = f"docs/releases/v{version}.md"
    if has_notes:
        (tmp_path / "docs" / "releases").mkdir(parents=True)
        (tmp_path / notes_path).write_text("Release notes", encoding="utf-8")

    args_path = tmp_path / "gh-args.txt"
    environment = os.environ.copy()
    environment["RELEASE_TAG"] = f"v{version}"
    mock_shell = 'gh() { printf "%s\\n" "$@" > gh-args.txt; }\n'
    result = subprocess.run(
        [bash, "-e", "-u", "-o", "pipefail", "-c", mock_shell + release_shell],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert args_path.read_text(encoding="utf-8").splitlines() == [
        "release",
        "create",
        f"v{version}",
        "--verify-tag",
        "--title",
        f"OpenCCForSigil v{version}",
        *release_flags,
        *(["--notes-file", notes_path] if has_notes else ["--generate-notes"]),
        *(f"release-artifacts/{asset}" for asset in assets),
    ]
