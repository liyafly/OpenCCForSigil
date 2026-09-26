"""Versioned persistence for rule sets referenced by profiles."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable, Mapping

from .models import Rule, RuleSnapshot
from .validators import RuleValidationError, validate_rules


RULESET_SCHEMA_VERSION = 2


class RuleSetFutureSchemaError(RuleValidationError):
    """The rule set uses a newer schema and must be preserved for a newer plugin."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


@dataclass(frozen=True)
class RuleSet:
    id: str
    rules: tuple[Rule, ...] = ()
    name: str = ""
    schema_version: int = RULESET_SCHEMA_VERSION
    semantic_version: int = 2
    default_direction: str = "*"
    default_scope: str = "global"
    enabled: bool = True

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuleSet":
        payload = migrate_ruleset_payload(payload)
        _validate_ruleset_payload_metadata(payload)
        identifier = payload.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            raise RuleValidationError("ruleset id must be a non-empty string")
        values = payload.get("rules")
        if not isinstance(values, list):
            raise RuleValidationError("ruleset rules must be an array")
        semantic_version = int(payload.get("semantic_version", 1))
        rules = []
        for item in values:
            if not isinstance(item, Mapping):
                rules.append(item)
                continue
            rule_payload = dict(item)
            rule_payload.setdefault("semantic_version", semantic_version)
            rules.append(Rule.from_dict(
                rule_payload,
                default_direction=(payload.get("default_direction", "*")
                                   if semantic_version >= 2 else None),
                default_scope=(payload.get("default_scope", "global")
                               if semantic_version >= 2 else "global"),
            ))
        return cls(
            identifier,
            validate_rules(rules),
            str(payload.get("name", "")),
            RULESET_SCHEMA_VERSION,
            semantic_version,
            str(payload.get("default_direction", "*")),
            str(payload.get("default_scope", "global")),
            payload.get("enabled", True),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "semantic_version": self.semantic_version,
            "default_direction": self.default_direction,
            "default_scope": self.default_scope,
            "enabled": self.enabled,
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
            value = RuleSet(
                ruleset.id, validate_rules(ruleset.rules), ruleset.name or name,
                RULESET_SCHEMA_VERSION, ruleset.semantic_version,
                ruleset.default_direction, ruleset.default_scope, ruleset.enabled,
            )
        else:
            identifier = str(ruleset.get("id", ""))
            value = RuleSet(
                identifier,
                validate_rules(rules if rules is not None else ruleset.get("rules", ())),
                str(ruleset.get("name", name)),
                RULESET_SCHEMA_VERSION,
                int(ruleset.get("semantic_version", 2)),
                str(ruleset.get("default_direction", "*")),
                str(ruleset.get("default_scope", "global")),
                ruleset.get("enabled", True),
            )
        _validate_ruleset_metadata(value)
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
            _backup_legacy_ruleset(destination)
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

    def list(self) -> tuple[tuple[RuleSet, ...], tuple[tuple[str, str], ...]]:
        if not self.directory.exists():
            return (), ()
        rulesets = []
        errors = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                rulesets.append(
                    RuleSet.from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, UnicodeError, json.JSONDecodeError, RuleValidationError) as exc:
                errors.append((path.name, str(exc)))
        return tuple(rulesets), tuple(errors)

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
    if isinstance(version, bool) or not isinstance(version, int):
        raise RuleValidationError(f"unsupported ruleset schema_version {version!r}; migration is required")
    if version == RULESET_SCHEMA_VERSION:
        _validate_ruleset_payload_metadata(result)
        return result
    if version > RULESET_SCHEMA_VERSION:
        raise RuleSetFutureSchemaError(
            f"unsupported future ruleset schema_version {version}; requires a newer plugin; "
            "file was not changed")
    if version in (0, 1):
        if not isinstance(result.get("rules"), list):
            raise RuleValidationError(
                "legacy ruleset requires a rules array; original file was not changed"
            )
        result.setdefault("semantic_version", 1)
        result.setdefault("default_direction", "*")
        result.setdefault("default_scope", "global")
        result.setdefault("enabled", True)
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


def _validate_ruleset_payload_metadata(payload: Mapping[str, Any]) -> None:
    semantic_version = payload.get("semantic_version", 1)
    if (not isinstance(semantic_version, int) or isinstance(semantic_version, bool)
            or semantic_version not in {1, 2}):
        raise RuleValidationError("ruleset semantic_version must be 1 or 2")
    direction = payload.get("default_direction", "*")
    from .models import SUPPORTED_DIRECTIONS, SUPPORTED_SCOPES

    if not isinstance(direction, str) or direction not in SUPPORTED_DIRECTIONS:
        raise RuleValidationError("ruleset default_direction must be a supported direction")
    scope = payload.get("default_scope", "global")
    if not isinstance(scope, str) or scope not in SUPPORTED_SCOPES - {"builtin"}:
        raise RuleValidationError("ruleset default_scope must be global, profile, or book")
    if not isinstance(payload.get("enabled", True), bool):
        raise RuleValidationError("ruleset enabled must be boolean")


def _validate_ruleset_metadata(ruleset: RuleSet) -> None:
    _validate_ruleset_payload_metadata({
        "semantic_version": ruleset.semantic_version,
        "default_direction": ruleset.default_direction,
        "default_scope": ruleset.default_scope,
        "enabled": ruleset.enabled,
    })


def _backup_legacy_ruleset(destination: Path) -> None:
    if not destination.is_file():
        return
    try:
        existing = json.loads(destination.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return
    version = existing.get("schema_version", 0) if isinstance(existing, dict) else 0
    if not isinstance(version, int) or isinstance(version, bool) or version >= RULESET_SCHEMA_VERSION:
        return
    backup = destination.with_suffix(destination.suffix + ".v1.bak")
    if not backup.exists():
        shutil.copy2(destination, backup)


__all__ = [
    "RULESET_SCHEMA_VERSION",
    "RuleSet",
    "RuleSetFutureSchemaError",
    "RuleStore",
    "load_ruleset",
    "migrate_ruleset_payload",
    "save_ruleset",
]
