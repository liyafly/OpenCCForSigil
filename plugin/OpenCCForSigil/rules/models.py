"""Rule model boundary."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RuleSnapshot:
    schema_version: int = 1
    rules_hash: str = ""
