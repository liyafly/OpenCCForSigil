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
from opencc_backend.integrity import sha256_tree
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


def _rewrite_selected_record(manifest_path: Path, payload_root: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for payload in manifest["payloads"]:
        if payload["payload_path"] == "payload":
            payload["payload_sha256"] = sha256_tree(payload_root)
            payload["native_plugins"] = {}
            break
    else:
        raise AssertionError("rewritten test payload is absent from manifest")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def _run_import_with_runfiles_probe(
    manifest_path: Path,
    marker_path: Path,
    script: str,
    **variables: Path,
) -> subprocess.CompletedProcess[str]:
    return _run_import_subprocess(
        manifest_path,
        """
import importlib.util
from pathlib import Path
import os

marker = Path(os.environ['MARKER'])
original_spec_from_file_location = importlib.util.spec_from_file_location

def probe(name, location, *args, **kwargs):
    location_path = Path(location)
    if name == 'opencc_clib' and any(part in {'src', 'pyd'} for part in location_path.parts):
        marker.write_text('runfiles probe executed', encoding='utf-8')
    return original_spec_from_file_location(name, location, *args, **kwargs)

importlib.util.spec_from_file_location = probe
"""
        + script,
        marker=marker_path,
        **variables,
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
print(json.dumps({'origin': origin, 'result': module.OpenCC('s2t').convert('汉字')}, ensure_ascii=True))
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
                  'loader': type(module.__spec__.loader).__name__}, ensure_ascii=True))
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
    (cache_tree / "__init__.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker_path)!r}).write_text('executed', encoding='utf-8')\n",
        encoding="utf-8",
    )
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
print(json.dumps({'origin': origin, 'result': module.OpenCC('s2t').convert('汉字')}, ensure_ascii=True))
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
                  'result': second.OpenCC('s2t').convert('汉字')}, ensure_ascii=True))
""",
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "same_package": True,
        "same_native": True,
        "result": "漢字",
    }


def test_import_verification_counts_cold_and_hot_paths(tmp_path: Path):
    manifest_path, payload_root = _copy_selected_payload(tmp_path)
    result = _run_import_subprocess(
        manifest_path,
        """
import json
import os
from pathlib import Path
import opencc_backend.runtime_selector as selector_module

calls = []
original_verify_tree = selector_module.verify_tree_sha256

def counted_verify_tree(root, expected):
    calls.append(Path(root))
    return original_verify_tree(root, expected)

selector_module.verify_tree_sha256 = counted_verify_tree
selector = selector_module.RuntimeSelector(manifest_path=Path(os.environ['MANIFEST']))
selector.import_opencc()
cold = len(calls)
selector.import_opencc()
print(json.dumps({'cold': cold, 'hot': len(calls) - cold}, ensure_ascii=True))
""",
        payload=payload_root,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"cold": 5, "hot": 1}


def test_delayed_import_rechecks_tampered_source_after_success(tmp_path: Path):
    manifest_path, payload_root = _copy_selected_payload(tmp_path)
    result = _run_import_subprocess(
        manifest_path,
        """
import importlib
import json
import os
import sys
from pathlib import Path
from app.errors import DataIntegrityError
from opencc_backend.runtime_selector import RuntimeSelector

RuntimeSelector(manifest_path=Path(os.environ['MANIFEST'])).import_opencc()
source_path = Path(os.environ['PAYLOAD']) / 'opencc' / 'cli.py'
source_path.write_bytes(source_path.read_bytes() + b'\\n# tampered after select\\n')
sys.modules.pop('opencc.cli', None)
try:
    importlib.import_module('opencc.cli')
except DataIntegrityError as exc:
    print(json.dumps({'error': type(exc).__name__, 'message': str(exc)}, ensure_ascii=True))
else:
    raise SystemExit('tampered delayed module unexpectedly imported')
""",
        payload=payload_root,
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["error"] == "DataIntegrityError"
    assert "payload SHA-256 mismatch" in output["message"]


def test_failed_import_clears_cached_context_before_next_import(tmp_path: Path):
    manifest_path, payload_root = _copy_selected_payload(tmp_path)
    result = _run_import_subprocess(
        manifest_path,
        """
import json
import os
import opencc_backend.runtime_selector as selector_module
from pathlib import Path

calls = []
original_verify_tree = selector_module.verify_tree_sha256

def counted_verify_tree(root, expected):
    calls.append(Path(root))
    return original_verify_tree(root, expected)

selector_module.verify_tree_sha256 = counted_verify_tree
selector = selector_module.RuntimeSelector(manifest_path=Path(os.environ['MANIFEST']))
selector.import_opencc()
original_origin = selector_module._verified_origin

def fail_origin(module, root):
    selector_module._verified_origin = original_origin
    raise RuntimeError('controlled import failure')

selector_module._verified_origin = fail_origin
try:
    selector.import_opencc()
except RuntimeError:
    pass
else:
    raise SystemExit('controlled import failure was not raised')
after_failure = sorted(
    name for name in __import__('sys').modules
    if name == 'opencc' or name.startswith('opencc.')
)
selector.import_opencc()
print(json.dumps({'modules_after_failure': after_failure,
                  'total_hashes': len(calls)}, ensure_ascii=True))
""",
        payload=payload_root,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "modules_after_failure": [],
        "total_hashes": 11,
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


def test_missing_native_cannot_fall_back_to_runfiles(tmp_path: Path):
    manifest_path, payload_root = _copy_selected_payload(tmp_path)
    native_path = next((payload_root / "opencc" / "clib").glob("opencc_clib.*"))
    native_path.unlink()
    _rewrite_selected_record(manifest_path, payload_root)

    runfiles_root = payload_root.parent
    runfiles_native = runfiles_root / "src" / "pyd" / "opencc_clib.so"
    runfiles_native.parent.mkdir(parents=True)
    runfiles_native.write_bytes(b"runfiles candidate")
    marker_path = tmp_path / "runfiles-probe"
    result = _run_import_with_runfiles_probe(
        manifest_path,
        marker_path,
        """
import json
import sys
from pathlib import Path
from opencc_backend.errors import PayloadIntegrityError
from opencc_backend.runtime_selector import RuntimeSelector, _PayloadImportFinder

try:
    RuntimeSelector(manifest_path=Path(os.environ['MANIFEST'])).import_opencc()
except PayloadIntegrityError as exc:
    print(json.dumps({'error': type(exc).__name__,
                      'finder': any(isinstance(item, _PayloadImportFinder) for item in sys.meta_path),
                      'modules': sorted(name for name in sys.modules if name == 'opencc' or name.startswith('opencc.'))}))
else:
    raise SystemExit('missing native module unexpectedly imported')
""",
    )
    assert result.returncode == 0, result.stderr
    assert not marker_path.exists()
    assert json.loads(result.stdout) == {"error": "PayloadIntegrityError", "finder": False, "modules": []}


def test_native_loader_error_cannot_fall_back_to_runfiles(tmp_path: Path):
    manifest_path, payload_root = _copy_selected_payload(tmp_path)
    native_path = next((payload_root / "opencc" / "clib").glob("opencc_clib.*"))
    native_path.write_bytes(b"corrupt native module")
    _rewrite_selected_record(manifest_path, payload_root)

    runfiles_root = payload_root.parent
    runfiles_native = runfiles_root / "src" / "pyd" / "opencc_clib.so"
    runfiles_native.parent.mkdir(parents=True)
    runfiles_native.write_bytes(b"runfiles candidate")
    marker_path = tmp_path / "runfiles-loader-probe"
    result = _run_import_with_runfiles_probe(
        manifest_path,
        marker_path,
        """
import json
import os
import sys
from pathlib import Path
from opencc_backend.errors import PayloadIntegrityError
from opencc_backend.runtime_selector import RuntimeSelector, _PayloadImportFinder

try:
    RuntimeSelector(manifest_path=Path(os.environ['MANIFEST'])).import_opencc()
except PayloadIntegrityError as exc:
    print(json.dumps({'error': type(exc).__name__,
                      'finder': any(isinstance(item, _PayloadImportFinder) for item in sys.meta_path),
                      'modules': sorted(name for name in sys.modules if name == 'opencc' or name.startswith('opencc.'))}))
else:
    raise SystemExit('corrupt native module unexpectedly imported')
""",
    )
    assert result.returncode == 0, result.stderr
    assert not marker_path.exists()
    assert json.loads(result.stdout) == {"error": "PayloadIntegrityError", "finder": False, "modules": []}


def test_out_of_payload_native_symlink_cannot_fall_back_to_runfiles(tmp_path: Path):
    manifest_path, payload_root = _copy_selected_payload(tmp_path)
    native_path = next((payload_root / "opencc" / "clib").glob("opencc_clib.*"))
    outside_native = tmp_path / "outside-native.so"
    outside_native.write_bytes(native_path.read_bytes())
    native_path.unlink()
    native_path.symlink_to(outside_native)
    _rewrite_selected_record(manifest_path, payload_root)

    runfiles_root = payload_root.parent
    runfiles_native = runfiles_root / "src" / "pyd" / "opencc_clib.so"
    runfiles_native.parent.mkdir(parents=True)
    runfiles_native.write_bytes(b"runfiles candidate")
    marker_path = tmp_path / "runfiles-symlink-probe"
    result = _run_import_with_runfiles_probe(
        manifest_path,
        marker_path,
        """
import json
import os
import sys
from pathlib import Path
from opencc_backend.errors import PayloadIntegrityError
from opencc_backend.runtime_selector import RuntimeSelector, _PayloadImportFinder

try:
    RuntimeSelector(manifest_path=Path(os.environ['MANIFEST'])).import_opencc()
except PayloadIntegrityError as exc:
    print(json.dumps({'error': type(exc).__name__,
                      'finder': any(isinstance(item, _PayloadImportFinder) for item in sys.meta_path),
                      'modules': sorted(name for name in sys.modules if name == 'opencc' or name.startswith('opencc.'))}))
else:
    raise SystemExit('out-of-payload native module unexpectedly imported')
""",
    )
    assert result.returncode == 0, result.stderr
    assert not marker_path.exists()
    assert json.loads(result.stdout) == {"error": "PayloadIntegrityError", "finder": False, "modules": []}
