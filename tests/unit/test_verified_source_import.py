from __future__ import annotations

import json
from importlib.util import cache_from_source
import os
from pathlib import Path
import py_compile
import shutil
import struct
import subprocess
import sys

import pytest

from app.errors import DataIntegrityError
from opencc_backend.runtime_selector import RuntimeSelector


ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugin" / "OpenCCForSigil"


def _copy_selected_payload(tmp_path: Path) -> tuple[Path, Path]:
    selector = RuntimeSelector()
    _, selected, source_root = selector.select()
    vendor_root = tmp_path / "vendor"
    vendor_root.mkdir()
    payload_root = vendor_root / "payload"
    shutil.copytree(source_root, payload_root)

    manifest = json.loads(selector.manifest_path.read_text(encoding="utf-8"))
    for payload in manifest["payloads"]:
        if payload["payload_path"] == selected.payload_path:
            payload["payload_path"] = "payload"
            break
    else:
        raise AssertionError(f"selected payload is absent from {selector.manifest_path}")
    manifest_path = vendor_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path, payload_root


def _write_timestamp_cache(source_path: Path, marker_path: Path, cache_path: Path) -> None:
    attack_source = cache_path.parent.parent.parent.parent / "cache_attack.py"
    attack_source.write_text(
        "from pathlib import Path\n"
        f"Path({str(marker_path)!r}).write_text('executed', encoding='utf-8')\n"
        "raise RuntimeError('malicious cache executed')\n",
        encoding="utf-8",
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    py_compile.compile(
        str(attack_source),
        cfile=str(cache_path),
        doraise=True,
        invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP,
    )
    cache = bytearray(cache_path.read_bytes())
    source_stat = source_path.stat()
    # A timestamp pyc is considered valid when these fields match the source;
    # the code object itself is intentionally compiled from the attack source.
    struct.pack_into("<II", cache, 8, int(source_stat.st_mtime), source_stat.st_size)
    cache_path.write_bytes(cache)


def _run_import_subprocess(manifest_path: Path, script: str, **variables: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    pythonpath = [str(PLUGIN_ROOT)]
    if environment.get("PYTHONPATH"):
        pythonpath.append(environment["PYTHONPATH"])
    environment["PYTHONPATH"] = os.pathsep.join(pythonpath)
    for name, value in variables.items():
        environment[name.upper()] = str(value)
    environment["MANIFEST"] = str(manifest_path)
    return subprocess.run(
        [
            sys.executable,
            "-c",
            script,
        ],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )


def test_valid_malicious_package_cache_is_never_executed(tmp_path: Path):
    manifest_path, payload_root = _copy_selected_payload(tmp_path)
    source_path = payload_root / "opencc" / "__init__.py"
    marker_path = tmp_path / "package-cache-executed"
    cache_path = Path(cache_from_source(str(source_path)))
    _write_timestamp_cache(source_path, marker_path, cache_path)

    result = _run_import_subprocess(
        manifest_path,
        """
import json
import os
from pathlib import Path
from opencc_backend.runtime_selector import RuntimeSelector

module, _, _, _, origin = RuntimeSelector(manifest_path=Path(os.environ['MANIFEST'])).import_opencc()
print(json.dumps({'origin': origin, 'result': module.OpenCC('s2t').convert('汉字')}, ensure_ascii=False))
""",
        marker=marker_path,
    )
    assert result.returncode == 0, result.stderr
    assert not marker_path.exists()
    assert json.loads(result.stdout) == {"origin": "opencc/__init__.py", "result": "漢字"}


def test_delayed_submodule_import_stays_source_only(tmp_path: Path):
    manifest_path, payload_root = _copy_selected_payload(tmp_path)
    source_path = payload_root / "opencc" / "cli.py"
    marker_path = tmp_path / "submodule-cache-executed"
    cache_path = Path(cache_from_source(str(source_path)))
    _write_timestamp_cache(source_path, marker_path, cache_path)

    result = _run_import_subprocess(
        manifest_path,
        """
import json
import importlib
import os
from pathlib import Path
from opencc_backend.runtime_selector import RuntimeSelector

RuntimeSelector(manifest_path=Path(os.environ['MANIFEST'])).import_opencc()
module = importlib.import_module('opencc.cli')
print(json.dumps({'origin': Path(module.__file__).relative_to(Path(os.environ['PAYLOAD'])).as_posix(),
                  'loader': type(module.__spec__.loader).__name__}, ensure_ascii=False))
""",
        marker=marker_path,
        payload=payload_root,
    )
    assert result.returncode == 0, result.stderr
    assert not marker_path.exists()
    assert json.loads(result.stdout) == {
        "origin": "opencc/cli.py",
        "loader": "_SourceOnlyLoader",
    }


def test_ignored_cache_tree_cannot_supply_an_opencc_submodule(tmp_path: Path):
    manifest_path, payload_root = _copy_selected_payload(tmp_path)
    marker_path = tmp_path / "cache-tree-executed"
    cache_tree = payload_root / "opencc" / "__pycache__"
    cache_tree.mkdir()
    (cache_tree / "evil.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker_path)!r}).write_text('executed', encoding='utf-8')\n",
        encoding="utf-8",
    )

    result = _run_import_subprocess(
        manifest_path,
        """
import importlib
import json
import os
from pathlib import Path
from opencc_backend.runtime_selector import RuntimeSelector

RuntimeSelector(manifest_path=Path(os.environ['MANIFEST'])).import_opencc()
try:
    importlib.import_module('opencc.__pycache__.evil')
except ImportError:
    print(json.dumps({'blocked': True}))
else:
    raise SystemExit('ignored cache tree was importable')
""",
    )
    assert result.returncode == 0, result.stderr
    assert not marker_path.exists()
    assert json.loads(result.stdout) == {"blocked": True}


def test_preloaded_opencc_modules_cannot_bypass_verified_import(tmp_path: Path):
    manifest_path, payload_root = _copy_selected_payload(tmp_path)
    result = _run_import_subprocess(
        manifest_path,
        """
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from opencc_backend.runtime_selector import RuntimeSelector

class FakeConverter:
    def convert(self, text):
        return 'BYPASSED'

fake_opencc = ModuleType('opencc')
fake_opencc.__file__ = str(Path(os.environ['PAYLOAD']) / 'opencc' / '__init__.py')
fake_opencc.__version__ = '1.4.2'
fake_opencc.OpenCC = lambda config: FakeConverter()
fake_clib = ModuleType('opencc.clib')
fake_clib.__file__ = str(Path(os.environ['PAYLOAD']) / 'opencc' / 'clib' / '__init__.py')
fake_native = ModuleType('opencc.clib.opencc_clib')
fake_native.__file__ = str(Path(os.environ['PAYLOAD']) / 'opencc' / 'clib' / 'opencc_clib.so')
fake_top_level = ModuleType('opencc_clib')
sys.modules.update({'opencc': fake_opencc, 'opencc.clib': fake_clib,
                    'opencc.clib.opencc_clib': fake_native, 'opencc_clib': fake_top_level})

module, _, _, _, origin = RuntimeSelector(manifest_path=Path(os.environ['MANIFEST'])).import_opencc()
print(json.dumps({'origin': origin, 'result': module.OpenCC('s2t').convert('汉字')}, ensure_ascii=False))
""",
        payload=payload_root,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"origin": "opencc/__init__.py", "result": "漢字"}


def test_repeated_verified_import_reuses_native_module():
    manifest_path = RuntimeSelector().manifest_path
    result = _run_import_subprocess(
        manifest_path,
        """
import json
import sys
from pathlib import Path
from opencc_backend.runtime_selector import RuntimeSelector

first, _, _, _, _ = RuntimeSelector(manifest_path=Path(__import__('os').environ['MANIFEST'])).import_opencc()
native = sys.modules['opencc.clib.opencc_clib']
second, _, _, _, _ = RuntimeSelector(manifest_path=Path(__import__('os').environ['MANIFEST'])).import_opencc()
print(json.dumps({'same_package': first is second,
                  'same_native': native is sys.modules['opencc.clib.opencc_clib'],
                  'result': second.OpenCC('s2t').convert('汉字')}, ensure_ascii=False))
""",
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "same_package": True,
        "same_native": True,
        "result": "漢字",
    }


def test_source_tampering_still_fails_integrity_check(tmp_path: Path):
    manifest_path, payload_root = _copy_selected_payload(tmp_path)
    source_path = payload_root / "opencc" / "__init__.py"
    source_path.write_bytes(source_path.read_bytes() + b"\n# tampered\n")

    with pytest.raises(DataIntegrityError, match="payload SHA-256 mismatch"):
        RuntimeSelector(manifest_path=manifest_path).select()


def test_native_tampering_still_fails_integrity_check(tmp_path: Path):
    manifest_path, payload_root = _copy_selected_payload(tmp_path)
    native_path = next((payload_root / "opencc" / "clib").glob("opencc_clib.*"))
    native_path.write_bytes(native_path.read_bytes() + b"tampered")

    with pytest.raises(DataIntegrityError, match="payload SHA-256 mismatch"):
        RuntimeSelector(manifest_path=manifest_path).select()
