from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.check_upstream_provenance import check


def _write_provenance(path: Path, **values: str) -> None:
    path.write_text(
        json.dumps({"schema_version": 1, **values}, ensure_ascii=False), encoding="utf-8"
    )


def test_upstream_provenance_check_emits_checkout_ref(monkeypatch, tmp_path: Path):
    values = {
        "opencc_version": "1.4.2",
        "opencc_upstream_tag": "ver.1.4.2",
        "opencc_upstream_commit": "a" * 40,
    }
    lock = tmp_path / "payload-lock.json"
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "github-output"
    _write_provenance(lock, **values)
    _write_provenance(manifest, **values)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    assert check(lock, manifest) == values["opencc_upstream_commit"]
    assert output.read_text(encoding="utf-8") == f"commit={values['opencc_upstream_commit']}\n"


def test_upstream_provenance_check_rejects_lock_manifest_mismatch(tmp_path: Path):
    lock = tmp_path / "payload-lock.json"
    manifest = tmp_path / "manifest.json"
    _write_provenance(
        lock,
        opencc_version="1.4.2",
        opencc_upstream_tag="ver.1.4.2",
        opencc_upstream_commit="a" * 40,
    )
    _write_provenance(
        manifest,
        opencc_version="1.4.2",
        opencc_upstream_tag="ver.1.4.2",
        opencc_upstream_commit="b" * 40,
    )

    with pytest.raises(SystemExit, match="opencc_upstream_commit"):
        check(lock, manifest)


def test_ci_cache_key_and_checkout_ref_use_provenance_inputs():
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "Check pinned OpenCC provenance before cache restore" in workflow
    assert "ref: ${{ steps.upstream.outputs.commit }}" in workflow
    cache_line = next(line for line in workflow.splitlines() if "hashFiles(" in line)
    for path in (
        ".github/workflows/ci.yml",
        "tools/export_verified_payload.py",
        "tools/merge_verified_payloads.py",
    ):
        assert path in cache_line
