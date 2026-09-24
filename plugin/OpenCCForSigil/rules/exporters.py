"""Deterministic rule export functions for supported interchange formats."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Iterable

from .models import Rule, RULE_SCHEMA_VERSION
from .validators import validate_rules


def export_rules(
    rules: Iterable[Rule],
    destination: str | Path | None = None,
    *,
    format: str = "json",
    enabled_only: bool = False,
    conflicts_only: bool = False,
) -> str:
    checked = validate_rules(rules)
    selected = tuple(rule for rule in checked if not enabled_only or rule.enabled)
    if conflicts_only:
        from .conflicts import blocking_conflicts

        ids = {item.id for conflict in blocking_conflicts(selected) for item in conflict.rules}
        selected = tuple(rule for rule in selected if rule.id in ids)
    fmt = format.lower().lstrip(".")
    if fmt == "json":
        text = (
            json.dumps(
                {
                    "schema_version": RULE_SCHEMA_VERSION,
                    "rules": [rule.to_dict() for rule in selected],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
    elif fmt in {"tsv", "tab"}:
        text = _delimited(selected, "\t")
    elif fmt == "csv":
        text = _delimited(selected, ",")
    elif fmt in {"txt", "opencc", "opencc-txt"}:
        text = "".join(
            f"{rule.source}\t{rule.target if rule.type == 'exact' else rule.source}\n"
            for rule in selected
            if not any(character.isspace() for character in rule.target)
        )
    else:
        raise ValueError(f"unsupported rule export format: {format}")
    if destination is not None:
        Path(destination).write_text(text, encoding="utf-8", newline="")
    return text


def export_warnings(
    rules: Iterable[Rule],
    *,
    format: str,
    enabled_only: bool = False,
    conflicts_only: bool = False,
) -> tuple[bool, int]:
    """Return whether export is lossy and how many TXT targets will be skipped."""

    checked = validate_rules(rules)
    selected = tuple(rule for rule in checked if not enabled_only or rule.enabled)
    if conflicts_only:
        from .conflicts import blocking_conflicts

        ids = {item.id for conflict in blocking_conflicts(selected) for item in conflict.rules}
        selected = tuple(rule for rule in selected if rule.id in ids)
    fmt = format.lower().lstrip(".")
    return _export_warnings(selected, fmt)


def _export_warnings(rules: Iterable[Rule], fmt: str) -> tuple[bool, int]:
    if fmt == "json":
        return False, 0
    if fmt in {"tsv", "tab", "csv", "txt", "opencc", "opencc-txt"}:
        lossy = any(
            not rule.enabled or rule.type == "protect" or rule.priority != 100
            for rule in rules
        )
        skipped_txt = (
            sum(any(character.isspace() for character in rule.target) for rule in rules)
            if fmt in {"txt", "opencc", "opencc-txt"}
            else 0
        )
        return lossy, skipped_txt
    raise ValueError(f"unsupported rule export format: {fmt}")


def _delimited(rules: Iterable[Rule], delimiter: str) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=delimiter, lineterminator="\n")
    writer.writerow(("direction", "source", "target", "comment"))
    for rule in sorted(rules, key=lambda item: item.id):
        writer.writerow(
            (
                rule.direction,
                rule.source,
                rule.source if rule.type == "protect" else rule.target,
                rule.comment,
            )
        )
    return output.getvalue()


def export_json(
    rules: Iterable[Rule], destination: str | Path | None = None, **kwargs: object
) -> str:
    return export_rules(rules, destination, format="json", **kwargs)


def export_tsv(
    rules: Iterable[Rule], destination: str | Path | None = None, **kwargs: object
) -> str:
    return export_rules(rules, destination, format="tsv", **kwargs)


def export_csv(
    rules: Iterable[Rule], destination: str | Path | None = None, **kwargs: object
) -> str:
    return export_rules(rules, destination, format="csv", **kwargs)


def export_opencc_txt(
    rules: Iterable[Rule], destination: str | Path | None = None, **kwargs: object
) -> str:
    return export_rules(rules, destination, format="opencc-txt", **kwargs)


__all__ = [
    "export_csv", "export_json", "export_opencc_txt", "export_rules", "export_tsv",
    "export_warnings",
]
