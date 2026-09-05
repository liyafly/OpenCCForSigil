"""Explicit conversion session state machine.

The Phase 0 controller only exercises the safe no-op path. The transition
table is already explicit so later UI work cannot replace it with unrelated
boolean flags.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Set, TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from logging_ext.logger import SessionLogger


class SessionState(str, Enum):
    IDLE = "idle"
    SCANNING = "scanning"
    ANALYZING = "analyzing"
    PLANNED = "planned"
    PREVIEWING = "previewing"
    APPLYING_TO_STAGE = "applying_to_stage"
    VERIFYING = "verifying"
    COMMITTING = "committing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


_ALLOWED_TRANSITIONS: Dict[SessionState, Set[SessionState]] = {
    SessionState.IDLE: {SessionState.SCANNING, SessionState.FAILED},
    SessionState.SCANNING: {
        SessionState.ANALYZING,
        SessionState.CANCELLED,
        SessionState.FAILED,
    },
    SessionState.ANALYZING: {
        SessionState.PLANNED,
        SessionState.CANCELLED,
        SessionState.FAILED,
    },
    # COMPLETED is allowed here only for the Phase 0 no-op path.
    SessionState.PLANNED: {
        SessionState.PREVIEWING,
        SessionState.COMPLETED,
        SessionState.CANCELLED,
        SessionState.FAILED,
    },
    SessionState.PREVIEWING: {
        SessionState.APPLYING_TO_STAGE,
        SessionState.CANCELLED,
        SessionState.FAILED,
    },
    SessionState.APPLYING_TO_STAGE: {
        SessionState.VERIFYING,
        SessionState.CANCELLED,
        SessionState.FAILED,
    },
    SessionState.VERIFYING: {
        SessionState.COMMITTING,
        SessionState.FAILED,
    },
    SessionState.COMMITTING: {
        SessionState.COMPLETED,
        SessionState.FAILED,
    },
    SessionState.COMPLETED: set(),
    SessionState.CANCELLED: set(),
    SessionState.FAILED: set(),
}


@dataclass
class Session:
    """A single auditable plugin run."""

    logger: Optional["SessionLogger"] = None
    session_id: str = field(default_factory=lambda: str(uuid4()))
    state: SessionState = SessionState.IDLE
    metadata: Dict[str, Any] = field(default_factory=dict)

    def transition(self, target: SessionState) -> None:
        """Move to *target* if the state machine permits the transition."""

        if target not in _ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(
                "invalid session transition: "
                f"{self.state.value} -> {target.value}"
            )

        previous = self.state
        self.state = target
        if self.logger is not None:
            self.logger.event(
                "state_transition",
                from_state=previous.value,
                to_state=target.value,
            )

    def complete_noop(self) -> None:
        """Complete the Phase 0 run without staging or writing book content."""

        self.transition(SessionState.COMPLETED)
