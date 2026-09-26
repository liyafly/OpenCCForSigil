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
            for rule in _opencc_txt_rules(selected)
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
        selected = tuple(rules)
        is_txt = fmt in {"txt", "opencc", "opencc-txt"}
        representable = _opencc_txt_rules(selected) if is_txt else selected
        skipped_txt = len(selected) - len(representable) if is_txt else 0
        if is_txt:
            # TXT has no columns for direction or scope. The importer requires
            # the user to choose a direction, so even a plain global dictionary
            # cannot be round-tripped without an explicit semantic loss.
            lossy = bool(representable) or skipped_txt > 0
        else:
            lossy = any(_delimited_loses_semantics(rule) for rule in selected)
        return lossy, skipped_txt
    raise ValueError(f"unsupported rule export format: {fmt}")


def _delimited_loses_semantics(rule: Rule) -> bool:
    """Whether legacy direction/source/target/comment rows change rule behavior."""

    return (
        not rule.enabled
        or rule.semantic_version != 1
        or rule.type != "exact"
        or rule.action != "override"
        or rule.match_type != "literal"
        or rule.stage != "source"
        or rule.scope != "global"
        or rule.priority != 100
        or bool(rule.source_note)
    )


def _opencc_txt_rules(rules: Iterable[Rule]) -> tuple[Rule, ...]:
    """Keep only enabled V1 literal final-wording rows safely represented by TXT."""

    return tuple(
        rule for rule in rules
        if rule.enabled
        and rule.semantic_version == 1
        and rule.type == "exact"
        and rule.action == "override"
        and rule.match_type == "literal"
        and rule.stage == "source"
        and bool(rule.target)
        and not rule.source.lstrip().startswith("#")
        and not any(character in "\t\r\n" for character in rule.source)
        and not any(character.isspace() for character in rule.target)
    )


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
