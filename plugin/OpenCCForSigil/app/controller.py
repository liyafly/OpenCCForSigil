"""Top-level application controller."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from app.session import Session, SessionState
from app.version import PLUGIN_VERSION
from core.models import ConvertRequest
from core.workflow import ConversionWorkflow
from document.tokenizer import TokenizerOptions
from logging_ext.logger import SessionLogger
from opencc_backend.backend import OpenCCBackend
from opencc_backend.configs import V1_CONFIGS
from sigil.adapter import SigilBookAdapter
from sigil.scope import Scope
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
        """Run preflight, preview, staging, verification, and commit."""

        self.logger.event("run_started", state=self.session.state.value)
        backend: Optional[OpenCCBackend] = None
        try:
            profile = _load_conservative_profile()
            preferences = self.storage.load_preferences(
                default={"last_conversion_config": str(profile["conversion"])}
            )
            default_config = _preferred_config(preferences, str(profile["conversion"]))
            self.session.transition(SessionState.SCANNING)
            backend = OpenCCBackend(default_config)
            self._run_backend_self_test(backend)

            if not _book_supports_conversion(self.bk):
                return self._complete_noop(
                    message="BookContainer text API unavailable; preflight-only run",
                )

            from ui.preview_window import choose_conversion_config, show_preview

            selected_config = choose_conversion_config(
                backend.available_configs(), default_config=default_config
            )
            if selected_config is None:
                self.session.cancel()
                self.logger.summary(
                    self._summary(status="cancelled", files_scanned=0, changes=0, files_changed=0)
                )
                return 1
            self.storage.save_preferences(
                {**preferences, "last_conversion_config": selected_config}
            )
            if selected_config != backend.config:
                backend.close()
                backend = OpenCCBackend(selected_config)
                self._run_backend_self_test(backend)

            self.session.transition(SessionState.ANALYZING)
            workflow = ConversionWorkflow(
                SigilBookAdapter(self.bk),
                backend,
                ConvertRequest(selected_config),
                scope=Scope(str(profile["scope"])),
                tokenizer_options=TokenizerOptions(
                    protected_elements=tuple(profile["protected_elements"]),
                    convert_attributes=tuple(profile["attributes"]),
                    svg_text=bool(profile["svg_text"]),
                    mathml=bool(profile["mathml"]),
                ),
                session_id=self.session.session_id,
                profile_id=str(profile["id"]),
            )
            planned = workflow.plan()
            planned_change_count = sum(len(item.plan.changes) for item in planned)
            self.logger.event(
                "plan_built",
                profile_id=profile["id"],
                config=selected_config,
                files_scanned=len(planned),
                changes=planned_change_count,
            )
            self.session.transition(SessionState.PLANNED)

            self.session.transition(SessionState.PREVIEWING)
            preview = show_preview(planned)
            if not preview.accepted:
                self.session.cancel()
                self.logger.summary(
                    self._summary(
                        status="cancelled",
                        files_scanned=len(planned),
                        changes=planned_change_count,
                        files_changed=0,
                    )
                )
                return 1

            finalized = workflow.finalize(preview.previews)
            accepted_change_count = sum(len(plan.changes) for _, plan in finalized)
            self.logger.event(
                "preview_completed",
                accepted_changes=accepted_change_count,
                planned_changes=planned_change_count,
            )

            self.session.transition(SessionState.APPLYING_TO_STAGE)
            staged = workflow.stage(finalized)
            self.session.transition(SessionState.VERIFYING)
            verification = workflow.verify(staged)
            self.logger.event(
                "verification_completed",
                files_verified=len(verification),
                passed=all(result.passed for result in verification),
            )
            self.session.transition(SessionState.COMMITTING)
            workflow.commit(staged)
            self.session.complete()
            self.logger.event(
                "commit_completed",
                files_changed=len(staged),
                changes=accepted_change_count,
            )
            self.logger.summary(
                self._summary(
                    status="success",
                    files_scanned=len(planned),
                    changes=accepted_change_count,
                    files_changed=len(staged),
                )
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
                self._summary(status="failed", files_scanned=0, changes=0, files_changed=0)
            )
            raise
        finally:
            if backend is not None:
                backend.close()

    def _run_backend_self_test(self, backend: OpenCCBackend) -> None:
        self_test = backend.self_test()
        self.logger.event(
            "backend_self_test",
            passed=self_test.passed,
            checks=self_test.checks,
            provenance=backend.provenance().as_dict(),
        )
        if not self_test.passed:
            raise RuntimeError(self_test.error or "official OpenCC backend self-test failed")

    def _complete_noop(
        self,
        *,
        message: str,
    ) -> int:
        self.session.transition(SessionState.ANALYZING)
        self.session.transition(SessionState.PLANNED)
        self.logger.event("skeleton_noop", message=message)
        self.session.complete_noop()
        self.logger.summary(
            self._summary(status="success", files_scanned=0, changes=0, files_changed=0)
        )
        return 0

    def _summary(
        self,
        *,
        status: str,
        files_scanned: int,
        changes: int,
        files_changed: int,
    ) -> Dict[str, object]:
        return {
            "plugin_version": PLUGIN_VERSION,
            "status": status,
            "state": self.session.state.value,
            "files_scanned": files_scanned,
            "files_changed": files_changed,
            "changes": changes,
        }


def _book_supports_conversion(book: Any) -> bool:
    return callable(getattr(book, "text_iter", None)) and callable(
        getattr(book, "readfile", None)
    )


def _preferred_config(preferences: Dict[str, object], fallback: str) -> str:
    candidate = preferences.get("last_conversion_config", fallback)
    return candidate if isinstance(candidate, str) and candidate in V1_CONFIGS else fallback


def _load_conservative_profile() -> Dict[str, object]:
    profile_path = (
        Path(__file__).resolve().parents[1] / "resources" / "defaults" / "conservative.json"
    )
    with profile_path.open("r", encoding="utf-8") as handle:
        profile = json.load(handle)
    if not isinstance(profile, dict):
        raise ValueError("conservative profile must be a JSON object")
    required = {
        "id",
        "conversion",
        "scope",
        "attributes",
        "protected_elements",
        "svg_text",
        "mathml",
    }
    missing = sorted(required - profile.keys())
    if missing:
        raise ValueError("conservative profile missing keys: " + ", ".join(missing))
    return profile
