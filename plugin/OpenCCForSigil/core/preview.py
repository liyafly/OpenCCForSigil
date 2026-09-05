"""Preview decisions over an immutable ConversionPlan.

The preview layer is intentionally UI-agnostic. A Tk/Qt view can map buttons
to accept_this/accept_all/reject_this without gaining access to the Sigil
BookContainer or the write path.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Dict, Optional, Tuple

from core.models import ConversionPlan, TokenChange


class PreviewDecision(str, Enum):
    ACCEPT_THIS = "accept_this"
    ACCEPT_ALL = "accept_all"
    REJECT_THIS = "reject_this"
    REJECT_ALL = "reject_all"
    CANCEL = "cancel"


@dataclass(frozen=True)
class PreviewFilter:
    """Optional scope for bulk decisions."""

    file_id: Optional[str] = None
    category: Optional[str] = None
    risk: Optional[str] = None
    rule_source: Optional[str] = None

    def matches(self, change: TokenChange) -> bool:
        return (
            (self.file_id is None or change.file_id == self.file_id)
            and (self.category is None or change.category == self.category)
            and (self.risk is None or change.risk == self.risk)
            and (self.rule_source is None or change.rule_source == self.rule_source)
        )


class PreviewError(ValueError):
    """Raised when a plan cannot be finalized safely."""


class PreviewSession:
    """Collect explicit per-change decisions without mutating the plan."""

    def __init__(self, plan: ConversionPlan) -> None:
        self.plan = plan
        self._changes: Dict[str, TokenChange] = {}
        for index, change in enumerate(plan.changes):
            change_id = change.change_id or f"change-{index}"
            if change_id in self._changes:
                raise PreviewError(f"duplicate preview change id: {change_id}")
            if not change.change_id:
                change = replace(change, change_id=change_id)
            self._changes[change_id] = change
        self._decisions: Dict[str, PreviewDecision] = {}

    @property
    def changes(self) -> Tuple[TokenChange, ...]:
        return tuple(self._changes.values())

    def decision(self, change_id: str) -> Optional[PreviewDecision]:
        self._require_change(change_id)
        return self._decisions.get(change_id)

    def undecided(self, scope: Optional[PreviewFilter] = None) -> Tuple[TokenChange, ...]:
        return tuple(
            change
            for change in self._changes.values()
            if change.change_id not in self._decisions
            and (scope is None or scope.matches(change))
        )

    def accept_this(self, change_id: str) -> None:
        self._set(change_id, PreviewDecision.ACCEPT_THIS)

    def reject_this(self, change_id: str) -> None:
        self._set(change_id, PreviewDecision.REJECT_THIS)

    def accept_all(self, scope: Optional[PreviewFilter] = None) -> int:
        return self._set_all(PreviewDecision.ACCEPT_ALL, scope)

    def reject_all(self, scope: Optional[PreviewFilter] = None) -> int:
        return self._set_all(PreviewDecision.REJECT_ALL, scope)

    def cancel(self) -> None:
        raise PreviewError("preview cancelled by user")

    def finalize(self, require_explicit: bool = True) -> ConversionPlan:
        remaining = self.undecided()
        if require_explicit and remaining:
            raise PreviewError(
                f"preview has {len(remaining)} undecided change(s); "
                "use Accept this, Reject this, Accept all, or Reject all"
            )
        accepted_ids = {
            change_id
            for change_id, decision in self._decisions.items()
            if decision in {PreviewDecision.ACCEPT_THIS, PreviewDecision.ACCEPT_ALL}
        }
        accepted = tuple(
            change
            for change in self._changes.values()
            if change.change_id in accepted_ids
        )
        return replace(
            self.plan,
            changes=accepted,
            allowed_spans=tuple(change.span for change in accepted),
        )

    def summary(self) -> Dict[str, int]:
        accepted = sum(
            decision in {PreviewDecision.ACCEPT_THIS, PreviewDecision.ACCEPT_ALL}
            for decision in self._decisions.values()
        )
        rejected = sum(
            decision in {PreviewDecision.REJECT_THIS, PreviewDecision.REJECT_ALL}
            for decision in self._decisions.values()
        )
        return {
            "total": len(self._changes),
            "accepted": accepted,
            "rejected": rejected,
            "undecided": len(self._changes) - accepted - rejected,
        }

    def _set(self, change_id: str, decision: PreviewDecision) -> None:
        self._require_change(change_id)
        self._decisions[change_id] = decision

    def _set_all(self, decision: PreviewDecision, scope: Optional[PreviewFilter]) -> int:
        selected = self.undecided(scope)
        for change in selected:
            self._decisions[change.change_id] = decision
        return len(selected)

    def _require_change(self, change_id: str) -> None:
        if change_id not in self._changes:
            raise PreviewError(f"unknown preview change id: {change_id}")


__all__ = [
    "PreviewDecision",
    "PreviewError",
    "PreviewFilter",
    "PreviewSession",
]
