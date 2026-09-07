import json
from pathlib import Path

import pytest

from tools.runtime_matrix import SUPPORTED_RUNTIME_IDENTITIES, runtime_identity
from tools.vendor_opencc import _verify_locked_wheel


def test_payload_lock_covers_every_supported_runtime():
    lock = json.loads(
        (Path(__file__).resolve().parents[2] / "native_build" / "payload-lock.json").read_text(
            encoding="utf-8"
        )
    )
    identities = {
        runtime_identity(entry)
        for entry in lock["wheels"]
    }
    assert identities == set(SUPPORTED_RUNTIME_IDENTITIES)


def test_payload_lock_rejects_changed_metadata(tmp_path):
    lock_path = tmp_path / "payload-lock.json"
    lock_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "wheels": [
                    {
                        "filename": "opencc.whl",
                        "url": "https://example.invalid/opencc.whl",
                        "sha256": "a",
                        "size": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="differs from payload lock"):
        _verify_locked_wheel(
            {
                "filename": "opencc.whl",
                "url": "https://example.invalid/other.whl",
                "sha256": "a",
                "size": 1,
            },
            lock_path=lock_path,
        )
