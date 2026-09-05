"""Per-session JSONL logging with a conservative privacy default."""

from datetime import datetime, timezone
import json
from pathlib import Path
import traceback
from typing import Any, Dict, Mapping, Optional
from uuid import uuid4

from logging_ext.jsonl import append_jsonl


class SessionLogger:
    """Write structured events and a summary for one plugin run.

    Callers should pass changed tokens and short context only. This class does
    not accept or persist an entire book/document payload as a special field.
    """

    def __init__(
        self,
        logs_root: Path,
        plugin_version: str,
        session_id: Optional[str] = None,
    ) -> None:
        self.session_id = session_id or str(uuid4())
        self.plugin_version = plugin_version
        month_root = logs_root / datetime.now(timezone.utc).strftime("%Y-%m")
        self.log_path = month_root / f"{self.session_id}.jsonl"
        self.summary_path = month_root / f"{self.session_id}.summary.json"

    def event(self, name: str, level: str = "INFO", **fields: Any) -> Dict[str, Any]:
        """Record and return a structured event."""

        event: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "session_id": self.session_id,
            "event": name,
        }
        event.update(fields)
        append_jsonl(self.log_path, event)
        return event

    def exception(self, name: str, error: Optional[BaseException] = None) -> None:
        """Record exception type/message and a DEBUG traceback."""

        exc = error
        self.event(
            name,
            level="ERROR",
            error_type=type(exc).__name__ if exc is not None else None,
            error=str(exc) if exc is not None else None,
            traceback=traceback.format_exc(),
        )

    def summary(self, values: Mapping[str, Any]) -> None:
        """Write the session summary atomically enough for Phase 0 use."""

        payload: Dict[str, Any] = {
            "schema_version": 1,
            "session_id": self.session_id,
            "plugin_version": self.plugin_version,
        }
        payload.update(values)
        self.summary_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.summary_path.with_suffix(".summary.json.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        temporary.replace(self.summary_path)
