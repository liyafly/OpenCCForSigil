from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

from tools.runtime_subset import (
    RuntimeSubsetError,
    derive_record,
    export_runtime_subset,
    sha256_tree,
    validate_derivation,
)


PLUGIN_DIR = "opencc/clib/lib64/opencc/plugins"
LIBRARY_PATH = PLUGIN_DIR + "/libopencc-jieba.so"


def _source_tree(root: Path, *, unknown: bool = False) -> dict[str, bytes]:
    files = {
        "opencc/__init__.py": b"__version__ = '1.4.2'\n",
        "opencc/cli.py": b"cli\n",
        "opencc/py.typed": b"",
        "opencc/clib/__init__.py": b"binding init\n",
        "opencc/clib/opencc_clib.cpython-314-win_arm64.pyd": b"binding",
        "opencc.libs/msvcp140-test.dll": b"runtime dll",
        "opencc/clib/share/opencc/s2t.json": b'{"conversion_chain": []}\n',
        "opencc/clib/share/opencc/STCharacters.ocd2": b"official dict",
        "opencc/clib/share/opencc/jieba_dict/jieba_merged.ocd2": b"merged",
        "opencc/clib/share/opencc/jieba_dict/hmm_model.utf8": b"hmm\n",
        "opencc/clib/share/opencc/jieba_dict/idf.utf8": b"idf\n",
        "opencc/clib/share/opencc/jieba_dict/stop_words.utf8": b"stop\n",
        "opencc/clib/share/opencc/jieba_dict/jieba.dict.utf8": b"fallback dict\n",
        "opencc/clib/share/opencc/jieba_dict/user.dict.utf8": b"fallback user\n",
        LIBRARY_PATH: b"native plugin",
        "opencc-1.4.2.dist-info/METADATA": b"Name: opencc\n",
        "opencc-1.4.2.dist-info/WHEEL": b"Tag: cp314\n",
        "opencc-1.4.2.dist-info/RECORD": b"original wheel receipt\n",
        "opencc-1.4.2.dist-info/top_level.txt": b"opencc\n",
        "opencc-1.4.2.dist-info/entry_points.txt": b"[console_scripts]\n",
        "opencc-1.4.2.dist-info/licenses/LICENSE": b"license",
        "opencc-1.4.2.dist-info/licenses/AUTHORS": b"authors",
        "opencc/clib/bin/opencc": b"cli binary",
        "opencc/clib/include/opencc/opencc.h": b"header",
        "opencc/clib/lib64/libopencc.a": b"static library",
        "opencc/clib/lib64/opencc/cmake/OpenCCConfig.cmake": b"cmake",
        "opencc/clib/lib64/pkgconfig/opencc.pc": b"pkgconfig",
    }
    if unknown:
        files["opencc/unknown-runtime.py"] = b"new upstream file"
    for relative, value in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    return files


def _record(root: Path, files: dict[str, bytes]) -> dict[str, object]:
    resources = {
        "opencc/clib/share/opencc/s2t.json": hashlib.sha256(
            files["opencc/clib/share/opencc/s2t.json"]
        ).hexdigest(),
    }
    for name in (
        "jieba_merged.ocd2",
        "hmm_model.utf8",
        "idf.utf8",
        "stop_words.utf8",
        "jieba.dict.utf8",
        "user.dict.utf8",
    ):
        relative = f"opencc/clib/share/opencc/jieba_dict/{name}"
        resources[relative] = hashlib.sha256(files[relative]).hexdigest()
    canonical = json.dumps(resources, sort_keys=True, separators=(",", ":")).encode()
    return {
        "wheel_sha256": "a" * 64,
        "payload_sha256": sha256_tree(root),
        "config_data": {"files": {}, "manifest_sha256": "b" * 64},
        "native_plugins": {
            "opencc-jieba": {
                "plugin_dir": PLUGIN_DIR,
                "library_path": LIBRARY_PATH,
                "resource_hashes": resources,
                "resource_manifest_sha256": hashlib.sha256(canonical).hexdigest(),
            }
        },
    }


def test_runtime_subset_preserves_allowed_bytes_and_removes_only_reviewed_paths(tmp_path: Path):
    source = tmp_path / "wheel"
    files = _source_tree(source)
    record = _record(source, files)
    destination = tmp_path / "subset"

    derived, receipt = derive_record(record, source, destination)

    assert (destination / "opencc.libs/msvcp140-test.dll").read_bytes() == b"runtime dll"
    assert (destination / LIBRARY_PATH).read_bytes() == b"native plugin"
    assert (destination / "opencc-1.4.2.dist-info/RECORD").read_bytes() == b"original wheel receipt\n"
    assert not (destination / "opencc/clib/bin/opencc").exists()
    assert not (destination / "opencc/clib/lib64/libopencc.a").exists()
    assert not (destination / "opencc/clib/include/opencc/opencc.h").exists()
    assert not (destination / "opencc/clib/share/opencc/jieba_dict/jieba.dict.utf8").exists()
    assert derived["record_describes"] == "source_wheel"
    assert derived["payload_sha256"] == sha256_tree(destination)
    assert receipt["source_tree_sha256"] == sha256_tree(source)
    assert {item["path"] for item in receipt["removed"]} == {
        "opencc/clib/bin/opencc",
        "opencc/clib/include/opencc/opencc.h",
        "opencc/clib/lib64/libopencc.a",
        "opencc/clib/lib64/opencc/cmake/OpenCCConfig.cmake",
        "opencc/clib/lib64/pkgconfig/opencc.pc",
        "opencc/clib/share/opencc/jieba_dict/jieba.dict.utf8",
        "opencc/clib/share/opencc/jieba_dict/user.dict.utf8",
    }
    for item in receipt["removed"]:
        source_file = source / item["path"]
        assert item["sha256"] == hashlib.sha256(source_file.read_bytes()).hexdigest()
        assert item["size"] == source_file.stat().st_size
    for path in destination.rglob("*"):
        if path.is_file():
            relative = path.relative_to(destination)
            assert path.read_bytes() == (source / relative).read_bytes()

    reconstructed = tmp_path / "reconstructed-source"
    shutil.copytree(destination, reconstructed)
    for item in receipt["removed"]:
        source_file = source / item["path"]
        output = reconstructed / item["path"]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(source_file.read_bytes())
    assert sha256_tree(reconstructed) == receipt["source_tree_sha256"]
    validate_derivation(
        derived,
        kept_paths=(path.relative_to(destination).as_posix() for path in destination.rglob("*") if path.is_file()),
        plugin_dir=PLUGIN_DIR,
        library_path=LIBRARY_PATH,
    )


def test_runtime_subset_export_is_deterministic_and_excludes_linux_lib64(tmp_path: Path):
    source = tmp_path / "wheel"
    _source_tree(source)

    first = tmp_path / "first"
    second = tmp_path / "second"
    first_hash, first_removed = export_runtime_subset(
        source, first, plugin_dir=PLUGIN_DIR, library_path=LIBRARY_PATH
    )
    second_hash, second_removed = export_runtime_subset(
        source, second, plugin_dir=PLUGIN_DIR, library_path=LIBRARY_PATH
    )

    assert first_hash == second_hash
    assert first_removed == second_removed
    assert not (first / "opencc/clib/lib64/libopencc.a").exists()
    assert (first / "opencc.libs/msvcp140-test.dll").read_bytes() == b"runtime dll"


def test_runtime_subset_rejects_unknown_upstream_files(tmp_path: Path):
    source = tmp_path / "wheel"
    _source_tree(source, unknown=True)

    with pytest.raises(RuntimeSubsetError, match="unreviewed OpenCC wheel files.*unknown-runtime.py"):
        export_runtime_subset(source, tmp_path / "subset", plugin_dir=PLUGIN_DIR, library_path=LIBRARY_PATH)
