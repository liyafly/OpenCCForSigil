#!/usr/bin/env python3
"""Measure HistoryStore.record_session/load cost as the unpruned index grows.

The store is created in a temporary directory under this script's folder;
no user history is read. Each synthetic session lists --files file entries
(hashes and counts only, as the controller's manifest does).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import shutil
import statistics
import sys
import tempfile
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import synthetic_book  # noqa: E402,F401

from logging_ext.history import HistoryStore, _validate_record  # noqa: E402


def session(index: int, files: int, when: datetime):
    session_id = str(uuid.UUID(int=index + 1))
    digest = hashlib.sha256(str(index).encode()).hexdigest()
    summary = {"session_id": session_id, "status": "success", "state": "completed",
               "files_scanned": files, "files_changed": files, "changes": files * 2000,
               "config": "s2t", "plugin_version": "0.2.8"}
    manifest = {"schema_version": 1, "session_id": session_id, "files": [
        {"id": f"chapter{n:04d}", "href": f"Text/chapter{n:04d}.xhtml",
         "before_sha256": digest, "after_sha256": digest, "bytes_before": 28000,
         "bytes_after": 28000, "change_count": 2000, "high_risk_changes": 0,
         "warnings": ["INLINE_BOUNDARY"] * 3} for n in range(files)]}
    provenance = {"opencc_version": "1.4.2", "config_name": "s2t", "payload_sha256": digest}
    return {"schema_version": 1, "session_id": session_id,
            "recorded_at": when.isoformat(), "summary": summary,
            "commit_manifest": manifest, "provenance": provenance}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", type=int, default=200)
    parser.add_argument("--sizes", default="0,50,200,1000")
    args = parser.parse_args()
    base = Path(tempfile.mkdtemp(prefix="history-probe-", dir=Path(__file__).resolve().parent))
    try:
        now = datetime(2026, 9, 28, tzinfo=timezone.utc)
        print("existing_sessions index_mib record_session_s load_s")
        for size in (int(value) for value in args.sizes.split(",")):
            root = base / f"h{size}"
            store = HistoryStore(root)
            store.replace_sessions(session(i, args.files, now - timedelta(minutes=i))
                                   for i in range(size))
            new = session(10**6, args.files, now + timedelta(minutes=1))
            samples = []
            for _ in range(3):
                start = time.perf_counter()
                store.record_session(new["summary"], new["commit_manifest"], new["provenance"],
                                     recorded_at=now + timedelta(minutes=1))
                samples.append(time.perf_counter() - start)
            start = time.perf_counter()
            loaded = store.load()
            load_seconds = time.perf_counter() - start
            assert len(loaded) == size + 1
            _validate_record(loaded[0])
            mib = store.index_path.stat().st_size / 2**20
            print(size, f"{mib:.1f}", f"{statistics.median(samples):.3f}", f"{load_seconds:.3f}")
    finally:
        shutil.rmtree(base)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
