"""Privacy-safe Markdown and JSON conversion report exports."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence


REPORT_SCHEMA_VERSION = 1
_TEXT_KEYS = frozenset(
    {"source", "target", "before", "after", "text", "content", "body", "full_diff", "diff"}
)


class ReportError(ValueError):
    """Raised when report inputs or report files are invalid."""


def report_schema_version() -> int:
    return REPORT_SCHEMA_VERSION


def _atomic_write(path: Path, content: str) -> Path:
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
            handle.write(content)
            handle.flush()
        temporary.replace(path)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise ReportError(f"could not write report: {path}") from exc
    return path


def _privacy_value(value: Any, *, key: str = "") -> Any:
    """Copy metadata while dropping accidental document text fields."""

    if key.lower() in _TEXT_KEYS:
        return None
    if isinstance(value, Mapping):
        result = {}
        for child_key, child_value in value.items():
            if not isinstance(child_key, str):
                continue
            cleaned = _privacy_value(child_value, key=child_key)
            if cleaned is not None:
                result[child_key] = cleaned
        return result
    if isinstance(value, (list, tuple)):
        return [_privacy_value(item, key=key) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _metadata(
    summary: Mapping[str, Any],
    commit_manifest: Mapping[str, Any],
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    if not all(isinstance(item, Mapping) for item in (summary, commit_manifest, provenance)):
        raise ReportError("report inputs must be JSON object mappings")
    return {
        "summary": _privacy_value(summary),
        "commit_manifest": _privacy_value(commit_manifest),
        "provenance": _privacy_value(provenance),
    }


def build_report(
    summary: Mapping[str, Any],
    commit_manifest: Mapping[str, Any],
    provenance: Mapping[str, Any],
    *,
    full_diff: Any = None,
    include_full_diff: bool = False,
) -> dict[str, Any]:
    """Build a report; full diff is included only by explicit opt-in."""

    if include_full_diff and full_diff is None:
        raise ReportError("full diff export requires an in-memory full_diff value")
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **_metadata(summary, commit_manifest, provenance),
    }
    if include_full_diff:
        report["full_diff"] = full_diff
    return report


def export_json(
    destination: Path,
    summary: Mapping[str, Any],
    commit_manifest: Mapping[str, Any],
    provenance: Mapping[str, Any],
    *,
    full_diff: Any = None,
    include_full_diff: bool = False,
) -> Path:
    """Atomically export a JSON report."""

    report = build_report(
        summary,
        commit_manifest,
        provenance,
        full_diff=full_diff,
        include_full_diff=include_full_diff,
    )
    return _atomic_write(
        destination,
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _summary_value(summary: Mapping[str, Any], key: str, default: Any = "") -> Any:
    value = summary.get(key, default)
    return value if isinstance(value, (str, int, float, bool)) or value is None else str(value)


def render_markdown(
    summary: Mapping[str, Any],
    commit_manifest: Mapping[str, Any],
    provenance: Mapping[str, Any],
    *,
    full_diff: Sequence[Mapping[str, Any]] | None = None,
    include_full_diff: bool = False,
) -> str:
    """Render a human-readable report without document text by default."""

    if include_full_diff and full_diff is None:
        raise ReportError("full diff export requires an in-memory full_diff value")
    report = build_report(
        summary,
        commit_manifest,
        provenance,
        full_diff=full_diff,
        include_full_diff=include_full_diff,
    )
    cleaned_summary = report["summary"]
    cleaned_manifest = report["commit_manifest"]
    cleaned_provenance = report["provenance"]
    lines = [
        "# OpenCC Conversion Report",
        "",
        f"- Session: `{_summary_value(cleaned_summary, 'session_id')}`",
        f"- Status: `{_summary_value(cleaned_summary, 'status')}`",
        f"- Profile: `{_summary_value(cleaned_summary, 'profile_id', _summary_value(cleaned_summary, 'profile'))}`",
        f"- Config: `{_summary_value(cleaned_summary, 'config')}`",
        f"- Files scanned: `{_summary_value(cleaned_summary, 'files_scanned', 0)}`",
        f"- Files changed: `{_summary_value(cleaned_summary, 'files_changed', 0)}`",
        f"- Changes: `{_summary_value(cleaned_summary, 'changes', 0)}`",
        "",
        "## Provenance",
        "",
    ]
    for key in (
        "backend_name",
        "opencc_version",
        "python_abi",
        "runtime_os",
        "runtime_architecture",
        "import_path_id",
    ):
        if key in cleaned_provenance:
            lines.append(f"- {key}: `{cleaned_provenance[key]}`")
    files = cleaned_manifest.get("files", []) if isinstance(cleaned_manifest, Mapping) else []
    lines.extend(
        [
            "",
            "## Files",
            "",
            "| File | Changes | Before SHA-256 | After SHA-256 |",
            "|---|---:|---|---|",
        ]
    )
    if isinstance(files, list):
        for item in files:
            if not isinstance(item, Mapping):
                continue
            lines.append(
                "| {href} | {count} | `{before}` | `{after}` |".format(
                    href=item.get("href", item.get("id", "")),
                    count=item.get("change_count", 0),
                    before=item.get("before_sha256", ""),
                    after=item.get("after_sha256", ""),
                )
            )
    if include_full_diff:
        lines.extend(["", "## Full Diff", ""])
        for item in full_diff or ():
            if isinstance(item, Mapping):
                lines.append(
                    f"- {item.get('href', item.get('file', ''))}: "
                    f"{item.get('source', '')} → {item.get('target', '')}"
                )
            else:
                lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def export_markdown(
    destination: Path,
    summary: Mapping[str, Any],
    commit_manifest: Mapping[str, Any],
    provenance: Mapping[str, Any],
    *,
    full_diff: Sequence[Mapping[str, Any]] | None = None,
    include_full_diff: bool = False,
) -> Path:
    """Atomically export a Markdown report."""

    return _atomic_write(
        destination,
        render_markdown(
            summary,
            commit_manifest,
            provenance,
            full_diff=full_diff,
            include_full_diff=include_full_diff,
        ),
    )


def validate_report(payload: Any) -> dict[str, Any]:
    """Validate and return report JSON without silently resetting corrupt data."""

    if not isinstance(payload, Mapping) or payload.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise ReportError("unsupported or malformed report schema")
    for key in ("summary", "commit_manifest", "provenance"):
        if not isinstance(payload.get(key), Mapping):
            raise ReportError(f"report field must be an object: {key}")
    return dict(payload)
