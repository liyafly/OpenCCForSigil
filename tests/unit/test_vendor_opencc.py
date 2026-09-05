from tools.vendor_opencc import _runtime_from_wheel


def test_runtime_from_wheel_preserves_macos_x86_64_tag():
    assert _runtime_from_wheel(
        "opencc-1.4.2-cp314-cp314-macosx_10_15_x86_64.whl"
    ) == ("CPython", 3, 14, "cp314", "macos", "x86_64")


def test_runtime_from_wheel_preserves_macos_arm64_tag():
    assert _runtime_from_wheel(
        "opencc-1.4.2-cp314-cp314-macosx_11_0_arm64.whl"
    ) == ("CPython", 3, 14, "cp314", "macos", "arm64")
