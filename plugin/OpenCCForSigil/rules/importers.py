"""TSV, CSV, JSON and OpenCC TXT rule importers."""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
import io
import json
from pathlib import Path
from typing import Any, Iterable, TextIO

from .conflicts import RuleConflict, find_conflicts
from .models import Rule, SUPPORTED_DIRECTIONS, new_rule_id
from .validators import RuleValidationError, validate_rule


@dataclass(frozen=True)
class ImportDiagnostic:
    line: int
    message: str
    severity: str = "warning"
    location: str = "line"
    message_key: str = ""


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

    return (rule.semantic_version, rule.enabled, rule.type, rule.action, rule.match_type,
            rule.stage, rule.direction, rule.scope, rule.source, rule.target, rule.priority,
            rule.profile_id if rule.scope == "profile" else "",
            rule.book_fingerprint if rule.scope == "book" else "")


def reassign_colliding_ids(rules: Iterable[Rule], existing_ids: Iterable[str]) -> tuple[Rule, ...]:
    """Return rules with fresh IDs wherever an ID is already in use."""

    used_ids = set(existing_ids)
    result = []
    for rule in rules:
        if rule.id in used_ids:
            identifier = new_rule_id()
            while identifier in used_ids:
                identifier = new_rule_id()
            rule = replace(rule, id=identifier)
        used_ids.add(rule.id)
        result.append(rule)
    return tuple(result)


def import_rules(
    source: str | bytes | Path | TextIO,
    *,
    format: str | None = None,
    direction: str | None = None,
    scope: str = "global",
    profile_id: str = "",
    book_fingerprint: str = "",
    rebind_owner: bool = False,
    semantic_version: int = 2,
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
            semantic_version=semantic_version,
            diagnostics=diagnostics,
            strict=strict,
            tsv=True,
        )
    elif fmt == "csv":
        values = _rows_to_rules(
            _delimited_rows(text, ","),
            direction=direction,
            scope=scope,
            profile_id=profile_id,
            book_fingerprint=book_fingerprint,
            semantic_version=semantic_version,
            diagnostics=diagnostics,
            strict=strict,
        )
    elif fmt in {"txt", "opencc", "opencc-txt"}:
        if not direction:
            raise RuleValidationError(
                "OpenCC TXT import requires an explicit direction", field="direction"
            )
        values = _opencc_rows(
            text, direction, scope, profile_id, book_fingerprint, diagnostics,
            semantic_version=semantic_version, strict=strict)
    elif fmt == "json":
        values = _json_rules(
            text,
            direction=direction,
            scope=scope,
            profile_id=profile_id,
            book_fingerprint=book_fingerprint,
            diagnostics=diagnostics,
            strict=strict,
            rebind_owner=rebind_owner,
        )
    else:
        raise ValueError(f"unsupported rule import format: {fmt}")
    valid: list[Rule] = []
    for line, value in values:
        try:
            valid.append(validate_rule(value, index=None))
        except RuleValidationError as exc:
            if strict:
                raise
            diagnostics.append(ImportDiagnostic(
                line, str(exc), "error", "record" if fmt == "json" else "line"))
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
    if delimiter == "\t":
        return [
            (line, row.split("\t"))
            for line, row in enumerate(text.lstrip("\ufeff").splitlines(), 1)
        ]
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    result = []
    for row in reader:
        result.append((reader.line_num, list(row)))
    return result


def _rows_to_rules(
    rows: Iterable[tuple[int, list[str]]],
    *,
    direction: str | None,
    scope: str,
    profile_id: str,
    book_fingerprint: str,
    semantic_version: int,
    diagnostics: list[ImportDiagnostic],
    strict: bool,
    tsv: bool = False,
) -> list[tuple[int, Rule]]:
    rows = list(rows)
    if rows and _is_header(rows[0][1]):
        rows.pop(0)
    result: list[tuple[int, Rule]] = []
    for line, row in rows:
        if not row or not any(value.strip() for value in row):
            continue
        try:
            first = row[0].strip() if row else ""
            has_direction = first in SUPPORTED_DIRECTIONS
            keep_legacy_blank_direction = len(row) >= 4 and not first
            if len(row) == 2:
                if not direction:
                    error = RuleValidationError(
                        "rules.import_needs_direction", field="direction", index=line)
                    error.message_key = "rules.import_needs_direction"
                    raise error
                row_direction, source, target = direction, row[0], row[1]
                comment = ""
            elif len(row) >= 3 and not has_direction and direction and not keep_legacy_blank_direction:
                row_direction, source, target = direction, row[0], row[1]
                comment = row[2]
            elif len(row) >= 3:
                row_direction, source, target = first or (direction or ""), row[1], row[2]
                comment = row[3] if len(row) > 3 else ""
            else:
                raise RuleValidationError(
                    "expected direction, source, target, comment", index=line)
            values = {
                "direction": row_direction,
                "source": source,
                "target": target,
                "scope": scope,
                "profile_id": profile_id,
                "book_fingerprint": book_fingerprint,
                "semantic_version": semantic_version,
                "action": "override",
                "match_type": "literal",
                "stage": "source",
            }
            if comment:
                values["comment"] = comment
            result.append((line, Rule.from_dict(values)))
            if tsv and any(_is_legacy_quoted_tsv_field(value) for value in row):
                diagnostics.append(ImportDiagnostic(
                    line,
                    "quoted field was imported literally",
                    "warning",
                    "line",
                    "rules.import_tsv_quoted_field",
                ))
        except RuleValidationError as exc:
            if strict:
                raise
            diagnostics.append(ImportDiagnostic(
                line, str(exc), "error", "line",
                getattr(exc, "message_key", ""),
            ))
    return result


def _is_legacy_quoted_tsv_field(value: str) -> bool:
    return (
        len(value) >= 2 and value.startswith('"') and value.endswith('"')
        and '""' in value[1:-1]
    )


def _opencc_rows(
    text: str,
    direction: str,
    scope: str,
    profile_id: str,
    book_fingerprint: str,
    diagnostics: list[ImportDiagnostic],
    *,
    semantic_version: int,
    strict: bool,
) -> list[tuple[int, Rule]]:
    result: list[tuple[int, Rule]] = []
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
                (line, Rule.from_dict(
                    {
                        "direction": direction,
                        "source": fields[0],
                        "target": candidates[0],
                        "scope": scope,
                        "profile_id": profile_id,
                        "book_fingerprint": book_fingerprint,
                        "semantic_version": semantic_version,
                        "action": "override",
                        "match_type": "literal",
                        "stage": "source",
                    }
                ))
            )
        except RuleValidationError as exc:
            if strict:
                raise
            diagnostics.append(ImportDiagnostic(line, str(exc), "error"))
    return result


def _json_rules(
    text: str, *, direction: str | None, scope: str, profile_id: str,
    book_fingerprint: str, diagnostics: list[ImportDiagnostic], strict: bool,
    rebind_owner: bool = False,
) -> list[tuple[int, Rule]]:
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
    result = []
    for index, value in enumerate(values, 1):
        try:
            if not isinstance(value, dict):
                raise RuleValidationError("rule record must be an object", index=index)
            rule = Rule.from_dict(
                value,
                default_direction=direction,
                default_scope=scope,
                profile_id=profile_id,
                book_fingerprint=book_fingerprint,
            )
            if rebind_owner and rule.scope == "profile":
                rule = replace(rule, profile_id=profile_id, book_fingerprint="")
            elif rebind_owner and rule.scope == "book":
                rule = replace(rule, profile_id="", book_fingerprint=book_fingerprint)
            result.append((index, rule))
        except (TypeError, ValueError) as exc:
            error = (exc if isinstance(exc, RuleValidationError) else
                     RuleValidationError(str(exc), index=index))
            if strict:
                raise error from exc
            diagnostics.append(ImportDiagnostic(index, str(error), "error", "record"))
    return result


def _is_header(row: list[str]) -> bool:
    if not row:
        return False
    return row[0].strip().casefold() in {
        "方向", "源", "源文本", "原文", "目标", "目标文本", "目標", "目標文字",
        "來源文字", "备注", "備註", "comment", "direction", "source", "target",
    }


__all__ = [
    "ImportDiagnostic",
    "ImportResult",
    "import_csv",
    "import_json",
    "import_opencc_txt",
    "import_rules",
    "import_tsv",
    "parse_rules",
    "reassign_colliding_ids",
    "rule_dedup_key",
]
