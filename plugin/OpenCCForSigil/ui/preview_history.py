"""Undo/redo record types for Preview decision history."""

from __future__ import annotations

from dataclasses import dataclass

from core.preview import (
    PreviewDecision,
)


@dataclass(frozen=True, slots=True)
class _DecisionHistoryChange:
    file_id: str
    change_id: str
    before: PreviewDecision | None
    after: PreviewDecision | None


@dataclass(frozen=True, slots=True)
class _DecisionHistoryOperation:
    sequence: int
    changes: tuple[_DecisionHistoryChange, ...]


@dataclass(frozen=True, slots=True)
class _ScopedBulkDecisionHistoryOperation:
    sequence: int
    before_decisions: tuple[tuple[str, tuple[str, ...], bytes], ...]
    after: PreviewDecision
    change_count: int

    @property
    def changes(self):
        return range(self.change_count)
