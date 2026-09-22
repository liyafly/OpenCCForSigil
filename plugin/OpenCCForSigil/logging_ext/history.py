"""Persistent, privacy-safe conversion history.

History stores completed-session metadata, commit hashes and counts.  It does
not store full document text or token diffs unless a caller explicitly exports
an in-memory diff through :mod:`logging_ext.report`.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable, Mapping

from logging_ext.report import _privacy_value


HISTORY_SCHEMA_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_SESSION_ID = re.compile(r"^[0-9a-fA-F-]{8,128}$")
_TEXT_KEYS = frozenset({"source", "target", "before", "after", "text", "content", "body", "diff"})


class HistoryError(ValueError):
    """Raised when history is corrupt, unsupported, or cannot be written."""


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
        temporary.replace(path)
    except (OSError, TypeError, ValueError) as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise HistoryError(f"could not write history: {path}") from exc


def _read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HistoryError(f"could not read history: {path}") from exc


def _parse_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise HistoryError(f"history {field} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HistoryError(f"history {field} is not a valid ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise HistoryError(f"history {field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _validate_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise HistoryError(f"history {field} must be a SHA-256 hex digest")
    return value.lower()


def _validate_files(files: Any) -> list[dict[str, Any]]:
    if not isinstance(files, list):
        raise HistoryError("history commit_manifest.files must be a list")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(files):
        if not isinstance(item, Mapping):
            raise HistoryError(f"history file entry {index} must be an object")
        file_id = item.get("id", item.get("href"))
        href = item.get("href", file_id)
        if not isinstance(file_id, str) or not file_id or not isinstance(href, str) or not href:
            raise HistoryError(f"history file entry {index} is missing id/href")
        change_count = item.get("change_count", 0)
        if not isinstance(change_count, int) or isinstance(change_count, bool) or change_count < 0:
            raise HistoryError(f"history file entry {index} has an invalid change_count")
        cleaned = {
            "id": file_id,
            "href": href,
            "before_sha256": _validate_sha(
                item.get("before_sha256"), f"files[{index}].before_sha256"
            ),
            "after_sha256": _validate_sha(item.get("after_sha256"), f"files[{index}].after_sha256"),
            "change_count": change_count,
        }
        for key in ("bytes_before", "bytes_after", "warnings", "high_risk_changes"):
            if key in item:
                value = item[key]
                if key == "warnings" and isinstance(value, list):
                    cleaned[key] = [str(entry) for entry in value]
                elif isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    cleaned[key] = value
        result.append(cleaned)
    return result


def _validate_commit_manifest(value: Any, session_id: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise HistoryError("commit_manifest must be an object")
    manifest_session = value.get("session_id", session_id)
    if manifest_session != session_id:
        raise HistoryError("commit_manifest session_id does not match summary")
    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "session_id": session_id,
        "files": _validate_files(value.get("files", [])),
    }


def _validate_record(record: Any) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise HistoryError("history session must be an object")
    if record.get("schema_version") != HISTORY_SCHEMA_VERSION:
        raise HistoryError("unsupported history session schema")
    session_id = record.get("session_id")
    if not isinstance(session_id, str) or not _SESSION_ID.fullmatch(session_id):
        raise HistoryError("history session_id is malformed")
    recorded_at = _parse_time(record.get("recorded_at"), "recorded_at")
    summary = record.get("summary")
    provenance = record.get("provenance")
    if not isinstance(summary, Mapping) or not isinstance(provenance, Mapping):
        raise HistoryError("history summary and provenance must be objects")
    if summary.get("session_id", session_id) != session_id:
        raise HistoryError("history summary session_id does not match")
    manifest = _validate_commit_manifest(record.get("commit_manifest"), session_id)
    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "session_id": session_id,
        "recorded_at": recorded_at.isoformat(),
        "summary": dict(_privacy_value(summary)),
        "commit_manifest": manifest,
        "provenance": dict(_privacy_value(provenance)),
    }


class HistoryStore:
    """Read and write ``history/index.json`` with visible corruption errors."""

    def __init__(self, history_root: Path) -> None:
        self.root = Path(history_root)
        self.index_path = self.root / "index.json"

    def load(self) -> list[dict[str, Any]]:
        if not self.index_path.exists():
            return []
        payload = _read_json(self.index_path)
        if (
            not isinstance(payload, Mapping)
            or payload.get("schema_version") != HISTORY_SCHEMA_VERSION
        ):
            raise HistoryError(f"unsupported history index schema: {self.index_path}")
        sessions = payload.get("sessions")
        if not isinstance(sessions, list):
            raise HistoryError(f"history sessions must be a list: {self.index_path}")
        validated = [_validate_record(item) for item in sessions]
        validated.sort(key=lambda item: item["recorded_at"], reverse=True)
        return validated

    def get(self, session_id: str) -> dict[str, Any]:
        for record in self.load():
            if record["session_id"] == session_id:
                return record
        raise HistoryError(f"history session not found: {session_id}")

    def record_session(
        self,
        summary: Mapping[str, Any],
        commit_manifest: Mapping[str, Any],
        provenance: Mapping[str, Any],
        *,
        recorded_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Record a completed session's summary, hashes/counts, and provenance."""

        if not isinstance(summary, Mapping):
            raise HistoryError("summary must be an object")
        session_id = summary.get("session_id")
        if not isinstance(session_id, str) or not _SESSION_ID.fullmatch(session_id):
            raise HistoryError("summary must contain a valid session_id")
        if summary.get("status") not in {"success", "completed"} or summary.get("state") not in {
            None,
            "completed",
        }:
            raise HistoryError("only completed sessions may be written to history")
        record = _validate_record(
            {
                "schema_version": HISTORY_SCHEMA_VERSION,
                "session_id": session_id,
                "recorded_at": (recorded_at or datetime.now(timezone.utc)).isoformat(),
                "summary": dict(_privacy_value(summary)),
                "commit_manifest": _validate_commit_manifest(commit_manifest, session_id),
                "provenance": dict(_privacy_value(provenance)),
            }
        )
        existing = [item for item in self.load() if item["session_id"] != session_id]
        existing.insert(0, record)
        _atomic_json(
            self.index_path,
            {"schema_version": HISTORY_SCHEMA_VERSION, "sessions": existing},
        )
        return record

    def replace_sessions(self, sessions: Iterable[Mapping[str, Any]]) -> None:
        validated = [_validate_record(item) for item in sessions]
        validated.sort(key=lambda item: item["recorded_at"], reverse=True)
        _atomic_json(
            self.index_path, {"schema_version": HISTORY_SCHEMA_VERSION, "sessions": validated}
        )

    def report_inputs(
        self, session_id: str
    ) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
        record = self.get(session_id)
        return record["summary"], record["commit_manifest"], record["provenance"]


def record_session(
    history_root: Path,
    summary: Mapping[str, Any],
    commit_manifest: Mapping[str, Any],
    provenance: Mapping[str, Any],
    *,
    recorded_at: datetime | None = None,
) -> dict[str, Any]:
    """Convenience API used by the controller integration."""

    return HistoryStore(history_root).record_session(
        summary,
        commit_manifest,
        provenance,
        recorded_at=recorded_at,
    )
