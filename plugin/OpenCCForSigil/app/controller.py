"""Top-level application controller.

The controller owns orchestration and state. It deliberately does not import
the UI, document processors, or official OpenCC backend. Phase 0 exposes a no-op path
so installation can be tested without mutating a book.
"""

from pathlib import Path
from typing import Any, Optional

from app.session import Session, SessionState
from app.version import PLUGIN_VERSION
from logging_ext.logger import SessionLogger
from sigil.storage import UserDataStore, resolve_user_data_dir


class Controller:
    """Coordinate one Sigil plugin invocation."""

    def __init__(self, bk: Any, data_dir: Optional[Path] = None) -> None:
        self.bk = bk
        root = Path(data_dir) if data_dir is not None else resolve_user_data_dir(bk)
        self.storage = UserDataStore(root)
        paths = self.storage.ensure_layout()
        self.logger = SessionLogger(paths.logs, plugin_version=PLUGIN_VERSION)
        self.session = Session(logger=self.logger, session_id=self.logger.session_id)

    def run(self) -> int:
        """Run the safe Phase 0 no-op flow and return a Sigil status code."""

        self.logger.event("run_started", state=self.session.state.value)
        try:
            self.session.transition(SessionState.SCANNING)
            self.session.transition(SessionState.ANALYZING)
            self.session.transition(SessionState.PLANNED)
            self.logger.event(
                "skeleton_noop",
                message="Phase 0 skeleton completed without modifying the book",
            )
            self.session.complete_noop()
            self.logger.summary(
                {
                    "plugin_version": PLUGIN_VERSION,
                    "status": "success",
                    "state": self.session.state.value,
                    "files_scanned": 0,
                    "files_changed": 0,
                    "changes": 0,
                }
            )
            return 0
        except Exception:
            if self.session.state not in {
                SessionState.COMPLETED,
                SessionState.CANCELLED,
                SessionState.FAILED,
            }:
                self.session.transition(SessionState.FAILED)
            self.logger.exception("controller_failed")
            self.logger.summary(
                {
                    "plugin_version": PLUGIN_VERSION,
                    "status": "failed",
                    "state": self.session.state.value,
                }
            )
            raise
