"""Versioned persistence for rule sets referenced by profiles."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping

from .models import Rule, RuleSnapshot
from .validators import RuleValidationError, validate_rules


RULESET_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class RuleSet:
    id: str
    rules: tuple[Rule, ...] = ()
    name: str = ""
    schema_version: int = RULESET_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuleSet":
        payload = migrate_ruleset_payload(payload)
        identifier = payload.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            raise RuleValidationError("ruleset id must be a non-empty string")
        values = payload.get("rules")
        if not isinstance(values, list):
            raise RuleValidationError("ruleset rules must be an array")
        return cls(
            identifier,
            validate_rules(values),
            str(payload.get("name", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "rules": [rule.to_dict() for rule in self.rules],
        }

    def snapshot(self) -> RuleSnapshot:
        return RuleSnapshot.freeze(self.rules)


class RuleStore:
    """Read/write separate rule-set files under the user-data rules directory."""

    def __init__(self, root: str | Path) -> None:
        root_path = Path(root)
        self.directory = root_path if root_path.name == "rules" else root_path / "rules"

    def save(
        self,
        ruleset: RuleSet | Mapping[str, Any],
        rules: Iterable[Rule] | None = None,
        *,
        name: str = "",
    ) -> Path:
        if isinstance(ruleset, RuleSet):
            value = RuleSet(ruleset.id, validate_rules(ruleset.rules), ruleset.name or name)
        else:
            identifier = str(ruleset.get("id", ""))
            value = RuleSet(
                identifier,
                validate_rules(rules if rules is not None else ruleset.get("rules", ())),
                str(ruleset.get("name", name)),
            )
        self._validate_id(value.id)
        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self.directory / f"{value.id}.json"
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{value.id}.", suffix=".tmp", dir=self.directory
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            temporary.write_text(
                json.dumps(value.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.replace(destination)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise RuleValidationError(f"could not save ruleset {value.id}: {exc}") from exc
        return destination

    def load(self, ruleset_id: str) -> RuleSet:
        self._validate_id(ruleset_id)
        path = self.directory / f"{ruleset_id}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RuleValidationError(f"ruleset not found: {ruleset_id}") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise RuleValidationError(f"could not read ruleset {ruleset_id}: {exc}") from exc
        return RuleSet.from_dict(payload)

    def load_many(self, ruleset_ids: Iterable[str]) -> tuple[Rule, ...]:
        result: list[Rule] = []
        for identifier in ruleset_ids:
            result.extend(self.load(str(identifier)).rules)
        return tuple(result)

    def load_snapshot(self, ruleset_ids: Iterable[str]) -> RuleSnapshot:
        return RuleSnapshot.freeze(self.load_many(ruleset_ids))

    def list(self) -> tuple[RuleSet, ...]:
        if not self.directory.exists():
            return ()
        return tuple(
            RuleSet.from_dict(json.loads(path.read_text(encoding="utf-8")))
            for path in sorted(self.directory.glob("*.json"))
        )

    @staticmethod
    def _validate_id(identifier: str) -> None:
        if (
            not identifier
            or identifier in {".", ".."}
            or any(char in identifier for char in ("/", "\\", ":", "\x00"))
        ):
            raise RuleValidationError("ruleset id must be a simple filename-safe identifier")


def migrate_ruleset_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise RuleValidationError("ruleset must be a JSON object")
    result = dict(payload)
    version = result.get("schema_version", 0)
    if version == RULESET_SCHEMA_VERSION:
        return result
    if version == 0:
        if not isinstance(result.get("rules"), list):
            raise RuleValidationError(
                "legacy ruleset requires a rules array; original file was not changed"
            )
        result["schema_version"] = RULESET_SCHEMA_VERSION
        return result
    raise RuleValidationError(
        f"unsupported ruleset schema_version {version!r}; migration is required"
    )


def save_ruleset(
    root: str | Path, ruleset_id: str, rules: Iterable[Rule], *, name: str = ""
) -> Path:
    return RuleStore(root).save(RuleSet(ruleset_id, tuple(rules), name))


def load_ruleset(root: str | Path, ruleset_id: str) -> RuleSet:
    return RuleStore(root).load(ruleset_id)


__all__ = [
    "RULESET_SCHEMA_VERSION",
    "RuleSet",
    "RuleStore",
    "load_ruleset",
    "migrate_ruleset_payload",
    "save_ruleset",
]
