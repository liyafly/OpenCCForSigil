import subprocess
import sys
from pathlib import Path


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
