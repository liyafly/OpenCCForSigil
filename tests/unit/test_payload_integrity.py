import os
from pathlib import Path

from opencc_backend import integrity
from opencc_backend.integrity import sha256_tree
from opencc_backend.runtime_selector import _PAYLOAD_TREE_DIGESTS, _verify_payload_tree
from opencc_backend.backend import OpenCCBackend
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


def test_backend_construction_hashes_payload_tree_once(monkeypatch):
    _PAYLOAD_TREE_DIGESTS.clear()
    calls = []
    original = integrity.verify_tree_sha256

    def counted(root, expected):
        calls.append(Path(root).resolve())
        return original(root, expected)

    monkeypatch.setattr("opencc_backend.runtime_selector.verify_tree_sha256", counted)
    first = OpenCCBackend("s2t")
    second = OpenCCBackend("t2s")
    try:
        assert first.convert("汉字") == "漢字"
        assert second.convert("汉字") == "汉字"
        assert len(calls) == 1
    finally:
        first.close()
        second.close()


def test_payload_tree_hash_cache_invalidates_when_mtime_changes(monkeypatch, tmp_path: Path):
    payload = tmp_path / "payload"
    payload.mkdir()
    member = payload / "opencc.py"
    member.write_bytes(b"official\n")
    expected = sha256_tree(payload)
    _PAYLOAD_TREE_DIGESTS.clear()
    calls = []
    original = integrity.verify_tree_sha256

    def counted(root, digest):
        calls.append(Path(root).resolve())
        return original(root, digest)

    monkeypatch.setattr("opencc_backend.runtime_selector.verify_tree_sha256", counted)

    assert _verify_payload_tree(payload, expected) == expected
    assert _verify_payload_tree(payload, expected) == expected
    assert len(calls) == 1

    stat = member.stat()
    os.utime(member, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
    assert _verify_payload_tree(payload, expected) == expected
    assert len(calls) == 2
