import pytest
import json
from pathlib import Path
import shutil

from tools.merge_verified_payloads import ROOT, _validate_jieba_resource_consistency, merge
from tools.runtime_subset import sha256_tree


def _record(*, os_name, architecture, payload_path, idf_hash, config_data):
    return {
        "python_implementation": "CPython",
        "python_version": "3.14",
        "python_abi": "cp314",
        "os": os_name,
        "architecture": architecture,
        "payload_path": payload_path,
        "payload_runtime_test": "passed",
        "payload_sha256": "",
        "config_data": config_data,
        "native_plugins": {
            "opencc-jieba": {
                "resource_hashes": {
                    "opencc/clib/share/opencc/jieba_dict/idf.utf8": idf_hash,
                },
            },
        },
    }


def test_merge_rejects_cross_payload_jieba_resource_hash_mismatch():
    config_data = {"source": "fixture", "manifest_sha256": "fixture", "files": {}}
    linux_record = _record(
        os_name="linux",
        architecture="x86_64",
        payload_path="payloads/linux-x86_64-cp314",
        idf_hash="b" * 64,
        config_data=config_data,
    )
    existing = _record(
        os_name="macos",
        architecture="arm64",
        payload_path="payloads/macos-arm64-cp314",
        idf_hash="a" * 64,
        config_data=config_data,
    )

    with pytest.raises(SystemExit, match="Jieba resource hash mismatch.*idf.utf8"):
        _validate_jieba_resource_consistency([existing, linux_record])


def test_merge_accepts_a_complete_tree_only_for_explicit_cache_restore(tmp_path: Path):
    source_vendor = ROOT / "plugin" / "OpenCCForSigil" / "vendor" / "opencc"
    source_manifest = json.loads((source_vendor / "manifest.json").read_text(encoding="utf-8"))
    record = source_manifest["payloads"][0]
    source_payload = source_vendor / record["payload_path"]
    cache_root = tmp_path / "cache"
    cache_entry = cache_root / "macos-arm64"
    cache_entry.mkdir(parents=True)
    complete_payload = cache_entry / "payload"
    shutil.copytree(source_payload, complete_payload)
    cli = complete_payload / "opencc" / "clib" / "bin" / "opencc"
    cli.parent.mkdir(parents=True, exist_ok=True)
    cli.write_bytes(b"official OpenCC CLI")
    complete_record = dict(record)
    complete_record.pop("record_describes", None)
    complete_record.pop("derivation", None)
    complete_record["payload_sha256"] = sha256_tree(complete_payload)
    (cache_entry / "record.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "record": complete_record,
                "config_data": complete_record["config_data"],
                "opencc_version": source_manifest["opencc_version"],
                "opencc_upstream_tag": source_manifest["opencc_upstream_tag"],
                "opencc_upstream_commit": source_manifest["opencc_upstream_commit"],
            }
        ),
        encoding="utf-8",
    )
    target_vendor = tmp_path / "vendor" / "opencc"
    target_vendor.mkdir(parents=True)
    shutil.copy2(source_vendor / "manifest.json", target_vendor / "manifest.json")

    with pytest.raises(SystemExit, match="payload artifact is not a runtime subset"):
        merge(cache_root, target_vendor)
    merge(cache_root, target_vendor, allow_full_source_payload=True)

    assert (target_vendor / record["payload_path"] / "opencc" / "clib" / "bin" / "opencc").is_file()
