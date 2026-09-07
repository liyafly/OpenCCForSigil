import subprocess
import sys
from pathlib import Path

from tools.build_plugin import build


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


def test_plugin_package_is_byte_for_byte_deterministic(tmp_path):
    first = build(tmp_path / "first.zip")
    second = build(tmp_path / "second.zip")

    assert first.read_bytes() == second.read_bytes()
