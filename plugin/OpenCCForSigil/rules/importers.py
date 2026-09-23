"""TSV, CSV, JSON and OpenCC TXT rule importers."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import io
import json
from pathlib import Path
from typing import Any, Iterable, TextIO

from .conflicts import RuleConflict, find_conflicts
from .models import Rule
from .validators import RuleValidationError, validate_rules


@dataclass(frozen=True)
class ImportDiagnostic:
    line: int
    message: str
    severity: str = "warning"


@dataclass(frozen=True)
class ImportResult:
    rules: tuple[Rule, ...]
    diagnostics: tuple[ImportDiagnostic, ...] = ()
    duplicates: tuple[Rule, ...] = ()
    conflicts: tuple[RuleConflict, ...] = ()

    @property
    def blocking(self) -> bool:
        return any(item.blocking for item in self.conflicts)


def rule_dedup_key(rule: Rule) -> tuple:
    """Return the stable semantic key shared by imports and the rule UI."""

    return (rule.direction, rule.scope, rule.type, rule.source, rule.target, rule.priority,
            rule.profile_id if rule.scope == "profile" else "",
            rule.book_fingerprint if rule.scope == "book" else "")


def import_rules(
    source: str | bytes | Path | TextIO,
    *,
    format: str | None = None,
    direction: str | None = None,
    scope: str = "global",
    profile_id: str = "",
    book_fingerprint: str = "",
    strict: bool = True,
) -> ImportResult:
    text, inferred = _read_source(source)
    fmt = (format or inferred or "json").lower().lstrip(".")
    diagnostics: list[ImportDiagnostic] = []
    if fmt in {"tsv", "tab"}:
        rows = _delimited_rows(text, "\t")
        values = _rows_to_rules(
            rows,
            direction=direction,
            scope=scope,
            profile_id=profile_id,
            book_fingerprint=book_fingerprint,
            diagnostics=diagnostics,
            strict=strict,
        )
    elif fmt == "csv":
        values = _rows_to_rules(
            _delimited_rows(text, ","),
            direction=direction,
            scope=scope,
            profile_id=profile_id,
            book_fingerprint=book_fingerprint,
            diagnostics=diagnostics,
            strict=strict,
        )
    elif fmt in {"txt", "opencc", "opencc-txt"}:
        if not direction:
            raise RuleValidationError(
                "OpenCC TXT import requires an explicit direction", field="direction"
            )
        values = _opencc_rows(
            text, direction, scope, profile_id, book_fingerprint, diagnostics, strict=strict)
    elif fmt == "json":
        values = _json_rules(
            text,
            direction=direction,
            scope=scope,
            profile_id=profile_id,
            book_fingerprint=book_fingerprint,
        )
    else:
        raise ValueError(f"unsupported rule import format: {fmt}")
    valid: list[Rule] = []
    for index, value in enumerate(values):
        try:
            valid.extend(validate_rules((value,)))
        except RuleValidationError as exc:
            if strict:
                raise
            diagnostics.append(ImportDiagnostic(index + 1, str(exc), "error"))
    unique: list[Rule] = []
    duplicates: list[Rule] = []
    seen: set[tuple] = set()
    for rule in valid:
        key = rule_dedup_key(rule)
        if key in seen:
            duplicates.append(rule)
        else:
            seen.add(key)
            unique.append(rule)
    conflicts = find_conflicts(unique)
    return ImportResult(tuple(unique), tuple(diagnostics), tuple(duplicates), tuple(conflicts))


def parse_rules(*args: Any, **kwargs: Any) -> ImportResult:
    return import_rules(*args, **kwargs)


def import_tsv(source: Any, **kwargs: Any) -> ImportResult:
    return import_rules(source, format="tsv", **kwargs)


def import_csv(source: Any, **kwargs: Any) -> ImportResult:
    return import_rules(source, format="csv", **kwargs)


def import_json(source: Any, **kwargs: Any) -> ImportResult:
    return import_rules(source, format="json", **kwargs)


def import_opencc_txt(source: Any, **kwargs: Any) -> ImportResult:
    return import_rules(source, format="opencc-txt", **kwargs)


def _read_source(source: str | bytes | Path | TextIO) -> tuple[str, str | None]:
    if hasattr(source, "read"):
        return str(source.read()).lstrip("\ufeff"), None
    if isinstance(source, Path):
        return source.read_text(encoding="utf-8-sig").lstrip("\ufeff"), source.suffix
    if isinstance(source, bytes):
        return source.decode("utf-8-sig").lstrip("\ufeff"), None
    value = str(source)
    path = Path(value)
    if "\n" not in value and path.exists():
        return path.read_text(encoding="utf-8-sig").lstrip("\ufeff"), path.suffix
    return value.lstrip("\ufeff"), None


def _delimited_rows(text: str, delimiter: str) -> list[tuple[int, list[str]]]:
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return [(index, list(row)) for index, row in enumerate(reader, 1)]


def _rows_to_rules(
    rows: Iterable[tuple[int, list[str]]],
    *,
    direction: str | None,
    scope: str,
    profile_id: str,
    book_fingerprint: str,
    diagnostics: list[ImportDiagnostic],
    strict: bool,
) -> list[Rule]:
    rows = list(rows)
    if rows and _is_header(rows[0][1]):
        rows.pop(0)
    result: list[Rule] = []
    for line, row in rows:
        if not row or not any(value.strip() for value in row):
            continue
        try:
            if len(row) < 3:
                raise RuleValidationError("expected direction, source, target, comment", index=line)
            values = {
                "direction": row[0].strip() or (direction or ""),
                "source": row[1],
                "target": row[2],
                "scope": scope,
                "profile_id": profile_id,
                "book_fingerprint": book_fingerprint,
            }
            if len(row) > 3:
                values["comment"] = row[3]
            result.append(Rule.from_dict(values))
        except RuleValidationError as exc:
            if strict:
                raise
            diagnostics.append(ImportDiagnostic(line, str(exc), "error"))
    return result


def _opencc_rows(
    text: str,
    direction: str,
    scope: str,
    profile_id: str,
    book_fingerprint: str,
    diagnostics: list[ImportDiagnostic],
    *,
    strict: bool,
) -> list[Rule]:
    result: list[Rule] = []
    for line, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        try:
            fields = raw.split("\t")
            if len(fields) < 2:
                raise RuleValidationError("expected source<TAB>target", index=line)
            candidates = fields[1].split()
            if not candidates:
                raise RuleValidationError("target is empty", index=line)
            if len(candidates) > 1:
                diagnostics.append(
                    ImportDiagnostic(line, "discarded candidates: " + " ".join(candidates[1:]))
                )
            result.append(
                Rule.from_dict(
                    {
                        "direction": direction,
                        "source": fields[0],
                        "target": candidates[0],
                        "scope": scope,
                        "profile_id": profile_id,
                        "book_fingerprint": book_fingerprint,
                    }
                )
            )
        except RuleValidationError as exc:
            if strict:
                raise
            diagnostics.append(ImportDiagnostic(line, str(exc), "error"))
    return result


def _json_rules(
    text: str, *, direction: str | None, scope: str, profile_id: str, book_fingerprint: str
) -> list[Rule]:
    payload = json.loads(text)
    if isinstance(payload, dict):
        values = payload.get("rules")
        if values is None:
            raise ValueError("JSON rule export must contain a 'rules' array")
    elif isinstance(payload, list):
        values = payload
    else:
        raise ValueError("JSON rule import must be an object or array")
    if not isinstance(values, list):
        raise ValueError("JSON rules must be an array")
    return [
        Rule.from_dict(
            value,
            default_direction=direction,
            default_scope=scope,
            profile_id=profile_id,
            book_fingerprint=book_fingerprint,
        )
        for value in values
    ]


def _is_header(row: list[str]) -> bool:
    normalized = {item.strip().lower() for item in row}
    return bool(normalized & {"direction", "source", "target"}) and "source" in normalized


__all__ = [
    "ImportDiagnostic",
    "ImportResult",
    "import_csv",
    "import_json",
    "import_opencc_txt",
    "import_rules",
    "import_tsv",
    "parse_rules",
    "rule_dedup_key",
]
