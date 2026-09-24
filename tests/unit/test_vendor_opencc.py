import json
from pathlib import Path

from tools import vendor_opencc
from tools.vendor_opencc import _runtime_from_wheel


def test_runtime_from_wheel_preserves_macos_x86_64_tag():
    assert _runtime_from_wheel(
        "opencc-1.4.2-cp314-cp314-macosx_10_15_x86_64.whl"
    ) == ("CPython", 3, 14, "cp314", "macos", "x86_64")


def test_runtime_from_wheel_preserves_macos_arm64_tag():
    assert _runtime_from_wheel(
        "opencc-1.4.2-cp314-cp314-macosx_11_0_arm64.whl"
    ) == ("CPython", 3, 14, "cp314", "macos", "arm64")


def test_runtime_from_wheel_preserves_linux_aarch64_tag():
    assert _runtime_from_wheel(
        "opencc-1.4.2-cp314-cp314-manylinux2014_aarch64.manylinux_2_17_aarch64.whl"
    ) == ("CPython", 3, 14, "cp314", "linux", "aarch64")


def test_runtime_from_wheel_accepts_linux_x86_64_cp312_tag():
    assert _runtime_from_wheel(
        "opencc-1.4.2-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl"
    ) == ("CPython", 3, 12, "cp312", "linux", "x86_64")


def test_host_wheel_selection_matches_the_running_python_minor(monkeypatch):
    lock_path = Path(__file__).resolve().parents[2] / "native_build" / "payload-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    wheels = lock["wheels"]
    monkeypatch.setattr(vendor_opencc, "_host_platform", lambda: ("linux", "x86_64"))

    selected = vendor_opencc._select_wheel(wheels, None, python_version=(3, 12))

    assert selected["python_abi"] == "cp312"
    assert selected["architecture"] == "x86_64"
