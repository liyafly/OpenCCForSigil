import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.version import supports_formal_runtime
from opencc_backend.backend import OpenCCBackend
from opencc_backend.errors import RuntimeSelectionError
from opencc_backend.manifest import RuntimeKey, VendorManifest
from opencc_backend import runtime_selector
from opencc_backend.runtime_selector import RuntimeSelector, detect_runtime


def test_manifest_is_official_binding_only_and_payload_is_exact():
    manifest = VendorManifest.load(
        RuntimeSelector().manifest_path
    )
    assert manifest.distribution_name == "opencc"
    assert manifest.import_name == "opencc"
    assert manifest.opencc_version == "1.4.2"
    assert manifest.python_compatibility["production_baseline"] == "3.14.2"
    assert manifest.python_compatibility["development_ci"] == "3.14.7"
    assert manifest.python_compatibility["patch_participates_in_payload_selection"] is False
    assert detect_runtime().python_abi.startswith("cp")
    assert detect_runtime().python_version.startswith("3.14.")
    runtime, payload, root = RuntimeSelector().select()
    assert runtime.compatibility_version == "3.14"
    assert payload.runtime == runtime.key
    assert root.is_dir()


def test_unmatched_runtime_fails_without_fallback():
    runtime = RuntimeKey("CPython", 3, 14, "cp314", "test-os", "test-arch")
    with pytest.raises(RuntimeSelectionError, match="no exact vendored OpenCC payload"):
        RuntimeSelector().manifest.select(runtime)


def test_linux_aarch64_runtime_selects_the_exact_payload(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(runtime_selector.sys, "platform", "linux")
    monkeypatch.setattr(runtime_selector.platform, "machine", lambda: "aarch64")
    runtime = detect_runtime()
    assert runtime.os == "linux"
    assert runtime.architecture == "aarch64"

    source = json.loads(RuntimeSelector().manifest_path.read_text(encoding="utf-8"))
    record = dict(source["payloads"][0])
    record["os"] = "linux"
    record["architecture"] = "aarch64"
    record["payload_path"] = "payloads/linux-aarch64-cp314"
    source["payloads"] = [record]
    source["config_data"]["payloads"] = {record["payload_path"]: record["config_data"]}
    manifest_path = tmp_path / "vendor" / "opencc" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps(source), encoding="utf-8")

    selected = RuntimeSelector(manifest_path=manifest_path).manifest.select(runtime.key)
    assert selected.payload_path == "payloads/linux-aarch64-cp314"


def test_backend_uses_official_binding_and_runs_self_test():
    backend = OpenCCBackend("s2t")
    assert backend.convert("汉字") == "漢字"
    assert set(backend.available_configs()) >= {
        "s2t",
        "t2s",
        "s2tw",
        "tw2s",
        "s2twp",
        "tw2sp",
        "s2hk",
        "hk2s",
        "s2hkp",
        "hk2sp",
        "t2tw",
        "t2hk",
        "tw2t",
        "hk2t",
    }
    assert backend.self_test().passed
    assert backend.provenance().python_version.startswith("3.14.")


def test_formal_runtime_accepts_any_314_patch_only():
    assert supports_formal_runtime("cpython", SimpleNamespace(major=3, minor=14, micro=2))
    assert supports_formal_runtime("cpython", SimpleNamespace(major=3, minor=14, micro=7))
    assert not supports_formal_runtime("cpython", SimpleNamespace(major=3, minor=13, micro=9))
    assert not supports_formal_runtime("cpython", SimpleNamespace(major=3, minor=15, micro=0))
    assert not supports_formal_runtime("pypy", SimpleNamespace(major=3, minor=14, micro=7))
