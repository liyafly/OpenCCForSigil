"""Metadata-only history search and filters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ui.i18n import Translator, configuration_label


def filter_history_records(
    records: Sequence[Mapping[str, Any]],
    *,
    query: str = "",
    status: str = "",
    direction: str = "",
    profile_names: Mapping[str, str] | None = None,
    translator: Any = None,
) -> list[Mapping[str, Any]]:
    """Apply ANDed metadata filters without reading history or log files."""

    tr = translator or Translator()
    names = profile_names or {}
    needle = str(query).strip().casefold()
    result = []
    for record in records:
        summary = record.get("summary", {})
        if not isinstance(summary, Mapping):
            summary = {}
        record_status = str(summary.get("status", "") or "")
        config = str(summary.get("config", "") or "")
        if status and record_status != status:
            continue
        if direction and config != direction:
            continue
        if needle:
            profile_id = str(summary.get("profile_id", summary.get("profile", "")) or "")
            values = (
                summary.get("book_label", ""), names.get(profile_id, ""), profile_id,
                config, configuration_label(tr, config) if config else "",
                record.get("session_id", ""),
            )
            if not any(needle in str(value or "").strip().casefold() for value in values):
                continue
        result.append(record)
    return result


__all__ = ["filter_history_records"]
