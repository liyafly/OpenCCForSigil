"""Explicit, plugin-owned history and log retention cleanup."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from typing import Any

from logging_ext.history import HistoryError, HistoryStore


_SESSION_FILE = re.compile(r"^(?P<session>[0-9a-fA-F-]{8,128})\.(?:jsonl|summary\.json)$")


@dataclass(frozen=True)
class RetentionResult:
    removed_sessions: tuple[str, ...] = ()
    removed_log_files: tuple[str, ...] = ()


def retention_policy() -> dict[str, int]:
    """Return defaults; this function never deletes anything."""

    return {"max_sessions": 50, "max_age_days": 30}


def _record_time(record: dict[str, Any]) -> datetime:
    value = record.get("recorded_at")
    if not isinstance(value, str):
        raise HistoryError("history recorded_at is missing")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def cleanup(
    history_root: Path,
    logs_root: Path,
    *,
    max_sessions: int = 50,
    max_age_days: int = 30,
    now: datetime | None = None,
    dry_run: bool = False,
) -> RetentionResult:
    """Explicitly remove old history and UUID-like session log files.

    This operation is separate from conversion. It rewrites only the owned
    history index and removes matching files in ``YYYY-MM`` log directories.
    """

    if max_sessions < 0 or max_age_days < 0:
        raise ValueError("retention limits must be non-negative")
    history = HistoryStore(Path(history_root))
    sessions = history.load()
    cutoff = (now or datetime.now(timezone.utc)).astimezone(timezone.utc) - timedelta(
        days=max_age_days
    )
    keep: list[dict[str, Any]] = []
    removed_sessions: list[str] = []
    for index, record in enumerate(sessions):
        timestamp = _record_time(record)
        if timestamp < cutoff or index >= max_sessions:
            removed_sessions.append(record["session_id"])
        else:
            keep.append(record)

    log_files: list[Path] = []
    logs_path = Path(logs_root)
    if logs_path.is_dir():
        for month in logs_path.iterdir():
            if month.is_symlink() or not month.is_dir() or not re.fullmatch(r"\d{4}-\d{2}", month.name):
                continue
            for path in month.iterdir():
                match = _SESSION_FILE.fullmatch(path.name)
                if (
                    path.is_file()
                    and not path.is_symlink()
                    and match is not None
                    and match.group("session") in removed_sessions
                ):
                    log_files.append(path)

    if not dry_run:
        if removed_sessions:
            history.replace_sessions(keep)
        for path in log_files:
            path.unlink()
    return RetentionResult(
        removed_sessions=tuple(removed_sessions),
        removed_log_files=tuple(str(path) for path in log_files),
    )


def cleanup_history(
    history_root: Path,
    logs_root: Path,
    *,
    max_sessions: int = 50,
    max_age_days: int = 30,
    now: datetime | None = None,
) -> RetentionResult:
    """Named cleanup entry point for explicit UI/application actions."""

    return cleanup(
        history_root,
        logs_root,
        max_sessions=max_sessions,
        max_age_days=max_age_days,
        now=now,
    )
