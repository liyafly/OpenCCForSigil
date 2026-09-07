from pathlib import Path

from opencc_backend.integrity import sha256_tree
from tools.build_opencc_jieba import _sha256_tree as jieba_sha256_tree
from tools.merge_verified_payloads import _sha256_tree as merge_sha256_tree
from tools.vendor_opencc import _sha256_tree as vendor_sha256_tree
from tools.verify_vendor import _sha256_tree as verify_sha256_tree


def test_generated_bytecode_does_not_change_payload_identity(tmp_path: Path):
    payload = tmp_path / "payload"
    (payload / "opencc").mkdir(parents=True)
    (payload / "opencc" / "__init__.py").write_bytes(b"official\n")
    before = {
        hasher(payload)
        for hasher in (
            sha256_tree,
            jieba_sha256_tree,
            merge_sha256_tree,
            vendor_sha256_tree,
            verify_sha256_tree,
        )
    }

    cache = payload / "opencc" / "__pycache__"
    cache.mkdir()
    (cache / "__init__.cpython-314.pyc").write_bytes(b"local cache")
    (payload / "generated.pyc").write_bytes(b"local cache")

    after = {
        hasher(payload)
        for hasher in (
            sha256_tree,
            jieba_sha256_tree,
            merge_sha256_tree,
            vendor_sha256_tree,
            verify_sha256_tree,
        )
    }
    assert len(before) == 1
    assert after == before
