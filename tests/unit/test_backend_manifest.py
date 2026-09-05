from types import SimpleNamespace

import pytest

from app.version import supports_formal_runtime
from opencc_backend.errors import RuntimeSelectionError
from opencc_backend.manifest import VendorManifest
from opencc_backend.runtime_selector import RuntimeSelector, detect_runtime


def test_phase0_manifest_is_official_binding_only():
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


def test_phase0_missing_payload_fails_without_fallback():
    with pytest.raises(RuntimeSelectionError):
        RuntimeSelector().select()


def test_formal_runtime_accepts_any_314_patch_only():
    assert supports_formal_runtime("cpython", SimpleNamespace(major=3, minor=14, micro=2))
    assert supports_formal_runtime("cpython", SimpleNamespace(major=3, minor=14, micro=7))
    assert not supports_formal_runtime("cpython", SimpleNamespace(major=3, minor=13, micro=9))
    assert not supports_formal_runtime("cpython", SimpleNamespace(major=3, minor=15, micro=0))
    assert not supports_formal_runtime("pypy", SimpleNamespace(major=3, minor=14, micro=7))
