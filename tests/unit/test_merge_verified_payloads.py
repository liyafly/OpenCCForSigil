import json

import pytest

from tools.merge_verified_payloads import _sha256_tree, merge


OPENCC_VERSION = "1.4.2"
UPSTREAM_TAG = "ver.1.4.2"
UPSTREAM_COMMIT = "025f371dc76b598d77384fbdab90c937471844d8"


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


def test_merge_rejects_cross_payload_jieba_resource_hash_mismatch(tmp_path):
    vendor = tmp_path / "vendor"
    payloads = vendor / "payloads"
    payloads.mkdir(parents=True)
    artifact_root = tmp_path / "artifacts"
    export = artifact_root / "linux"
    payload = export / "payload"
    payload.mkdir(parents=True)
    (payload / "placeholder").write_bytes(b"verified target payload")
    config_data = {"source": "fixture", "manifest_sha256": "fixture", "files": {}}
    linux_record = _record(
        os_name="linux",
        architecture="x86_64",
        payload_path="payloads/linux-x86_64-cp314",
        idf_hash="b" * 64,
        config_data=config_data,
    )
    linux_record["payload_sha256"] = _sha256_tree(payload)
    (export / "record.json").write_text(json.dumps({
        "schema_version": 1,
        "opencc_version": OPENCC_VERSION,
        "opencc_upstream_tag": UPSTREAM_TAG,
        "opencc_upstream_commit": UPSTREAM_COMMIT,
        "config_data": config_data,
        "record": linux_record,
    }), encoding="utf-8")

    existing = _record(
        os_name="macos",
        architecture="arm64",
        payload_path="payloads/macos-arm64-cp314",
        idf_hash="a" * 64,
        config_data=config_data,
    )
    manifest = {
        "opencc_version": OPENCC_VERSION,
        "opencc_upstream_tag": UPSTREAM_TAG,
        "opencc_upstream_commit": UPSTREAM_COMMIT,
        "payloads": [existing],
    }
    (vendor / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SystemExit, match="Jieba resource hash mismatch.*idf.utf8"):
        merge(artifact_root, vendor)
