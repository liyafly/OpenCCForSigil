from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tomllib
import xml.etree.ElementTree as ET

import pytest

from app.version import PLUGIN_VERSION
from tools.build_plugin import validate as validate_plugin


ROOT = Path(__file__).resolve().parents[2]


def test_current_plugin_metadata_and_project_versions_are_consistent():
    plugin_xml = ET.parse(ROOT / "plugin" / "OpenCCForSigil" / "plugin.xml").getroot()
    assert PLUGIN_VERSION == "0.1.0"
    assert plugin_xml.findtext("version") == PLUGIN_VERSION
    assert plugin_xml.findtext("author") == "liyafly"

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == "0.1.0"

    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    project = next(
        package for package in lock["package"] if package["name"] == "opencc-for-sigil"
    )
    assert project["version"] == "0.1.0"
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


def test_ci_and_release_contract_uses_sha_then_versioned_product_asset():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    release_job = workflow.split("  publish-release:", maxsplit=1)[1]
    release_shell = _extract_run_block(release_job, "Create GitHub release")

    assert "build_spec_bundle.py" not in workflow
    assert "OpenCCForSigil_Spec_v1.4_bundle.zip" not in workflow
    assert "spec_zip" not in release_job
    assert "spec-bundle" not in (ROOT / "Makefile").read_text(encoding="utf-8")
    assert not (ROOT / "tools" / "build_spec_bundle.py").exists()
    assert "OpenCCForSigil-fat-plugin-${{ github.sha }}" in workflow
    assert "dist/OpenCCForSigil_${{ github.sha }}.zip" in workflow
    assert release_shell.count("gh release create") == 1
    assert '"release-artifacts/OpenCCForSigil_${version}.zip"' in release_shell


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
    (release_artifacts / f"OpenCCForSigil_{version}.zip").write_bytes(b"plugin artifact")
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
        f"release-artifacts/OpenCCForSigil_{version}.zip",
    ]
