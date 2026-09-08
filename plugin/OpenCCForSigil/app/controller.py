"""Top-level application controller."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from app.session import Session, SessionState
from app.version import PLUGIN_VERSION
from core.models import ConvertRequest
from core.workflow import ConversionWorkflow, WorkflowCancelled, WorkflowCommitError
from document.tokenizer import TokenizerOptions
from logging_ext.logger import SessionLogger
from opencc_backend.backend import OpenCCBackend
from opencc_backend.configs import SUPPORTED_CONFIGS, is_jieba_config
from sigil.adapter import SigilBookAdapter
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
        self._running = False

    def run(self) -> int:
        """Run one invocation, rejecting re-entrant or terminal sessions."""

        if self._running or self.session.state is not SessionState.IDLE:
            self.logger.event("run_reentry_blocked", state=self.session.state.value)
            return 1
        self._running = True
        try:
            return self._run_once()
        finally:
            self._running = False

    def _run_once(self) -> int:
        """Run preflight, preview, staging, verification, and commit."""

        self.logger.event("run_started", state=self.session.state.value)
        backend: Optional[OpenCCBackend] = None
        planned = ()
        staged = ()
        planned_change_count = 0
        files_without_changes = 0
        accepted_change_count = 0
        skipped_change_count = 0
        try:
            profile = _load_conservative_profile()
            preferences = self.storage.load_preferences(
                default={
                    "last_conversion_config": str(profile["conversion"]),
                    "ui": {},
                }
            )
            default_config = _preferred_config(preferences, str(profile["conversion"]))
            self.session.transition(SessionState.SCANNING)
            # Always preflight the stable standard backend first. An optional
            # Jieba preference is resolved only after the selected payload has
            # advertised and verified the native plugin capability.
            backend = OpenCCBackend("s2t")
            self._run_backend_self_test(backend)

            if not _book_supports_conversion(self.bk):
                return self._complete_noop(
                    message="BookContainer text API unavailable; preflight-only run",
                )

            from ui.i18n import choose_language
            from ui.preview_window import (
                choose_conversion_config,
                choose_scope,
                create_progress_reporter,
                set_ui_language,
                show_result,
                show_preview,
            )

            raw_ui_preferences = preferences.get("ui")
            # Corrupt or legacy preference files must not make a conversion
            # crash while merging the UI namespace.  Preserve valid unknown UI
            # keys, but normalize every other value to an empty mapping.
            ui_preferences = dict(raw_ui_preferences) if isinstance(raw_ui_preferences, dict) else {}
            explicit_language = ui_preferences.get("language")
            host_language = getattr(self.bk, "sigil_ui_lang", None)
            language = choose_language(explicit_language, host_language)
            set_ui_language(language)

            adapter = SigilBookAdapter(self.bk)
            # Text-capable hosts always get an explicit scope chooser.  A host
            # without selected_iter simply opens it with no initial checks; it
            # must never silently widen the run to ALL_XHTML.
            scope_outcome = choose_scope(adapter, initial_language=language)
            language = scope_outcome.language
            set_ui_language(language)
            scope_preferences = {
                **preferences,
                "ui": {**ui_preferences, "language": language},
            }
            if not scope_outcome.accepted or scope_outcome.selection is None:
                self.storage.save_preferences(scope_preferences)
                self.session.cancel()
                self.logger.summary(
                    self._summary(status="cancelled", files_scanned=0, changes=0, files_changed=0)
                )
                return 1
            targets = scope_outcome.selection

            # The language choice is now settled before the direction dialog
            # is constructed, including on a first launch with no preference.
            selected_config = choose_conversion_config(
                backend.available_configs(), default_config=default_config
            )
            if selected_config is None:
                self.storage.save_preferences(scope_preferences)
                self.session.cancel()
                self.logger.summary(
                    self._summary(status="cancelled", files_scanned=0, changes=0, files_changed=0)
                )
                return 1
            self.storage.save_preferences(
                {
                    **preferences,
                    "last_conversion_config": selected_config,
                    "ui": {**ui_preferences, "language": language},
                }
            )
            if selected_config != backend.config:
                backend.close()
                backend = OpenCCBackend(selected_config)
                self._run_backend_self_test(backend)

            self.session.transition(SessionState.ANALYZING)
            workflow = ConversionWorkflow(
                adapter,
                backend,
                ConvertRequest(
                    selected_config,
                    segmentation="jieba" if is_jieba_config(selected_config) else "mmseg",
                ),
                scope=targets.scope,
                targets=targets,
                tokenizer_options=TokenizerOptions(
                    protected_elements=tuple(profile["protected_elements"]),
                    convert_attributes=tuple(profile["attributes"]),
                    svg_text=bool(profile["svg_text"]),
                    mathml=bool(profile["mathml"]),
                ),
                session_id=self.session.session_id,
                profile_id=str(profile["id"]),
            )
            progress = create_progress_reporter(len(targets.file_ids))
            try:
                planned = workflow.plan(
                    progress=progress.update,
                    cancelled=progress.cancelled,
                )
            except WorkflowCancelled:
                self.session.cancel()
                self.logger.summary(
                    self._summary(status="cancelled", files_scanned=0, changes=0, files_changed=0)
                )
                _show_result_safely(
                    show_result,
                    status="cancelled",
                    files_scanned=0,
                    files_changed=0,
                    accepted_changes=0,
                    skipped_changes=0,
                )
                return 1
            finally:
                progress.close()
            planned_change_count = sum(len(item.plan.changes) for item in planned)
            files_without_changes = sum(not item.plan.changes for item in planned)
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
                        files_without_changes=files_without_changes,
                    )
                )
                return 1

            finalized = workflow.finalize(preview.previews)
            accepted_change_count = sum(len(plan.changes) for _, plan in finalized)
            skipped_change_count = planned_change_count - accepted_change_count
            self.logger.event(
                "preview_completed",
                accepted_changes=accepted_change_count,
                planned_changes=planned_change_count,
            )

            self.session.transition(SessionState.APPLYING_TO_STAGE)
            post_preview_progress = create_progress_reporter(len(planned))
            try:
                # Staging and verification happen before the write boundary;
                # keep the user informed without offering a cancellation
                # action that cannot safely interrupt these phases.
                disable_cancel = getattr(post_preview_progress, "disable_cancel", None)
                if callable(disable_cancel):
                    disable_cancel()
                staged = workflow.stage(
                    finalized,
                    progress=post_preview_progress.update,
                )
                self.session.transition(SessionState.VERIFYING)
                verification = workflow.verify(
                    staged,
                    progress=post_preview_progress.update,
                )
            finally:
                post_preview_progress.close()
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
                    files_without_changes=files_without_changes,
                    skipped_changes=skipped_change_count,
                )
            )
            _show_result_safely(
                show_result,
                status="success",
                files_scanned=len(planned),
                files_changed=len(staged),
                accepted_changes=accepted_change_count,
                skipped_changes=skipped_change_count,
                files_not_written=max(0, len(planned) - len(staged)),
                files_without_changes=files_without_changes,
            )
            return 0
        except WorkflowCommitError as exc:
            if self.session.state not in {
                SessionState.COMPLETED,
                SessionState.CANCELLED,
                SessionState.FAILED,
            }:
                self.session.transition(SessionState.FAILED)
            committed = set(exc.committed_file_ids)
            files_changed = len(committed)
            accepted = sum(
                len(item.plan.changes) for item in staged if item.file_id in committed
            )
            self.logger.exception("controller_commit_failed", exc)
            self.logger.event(
                "commit_partial_failure",
                committed_file_ids=sorted(committed),
                failed_file_id=exc.failed_file_id,
            )
            self.logger.summary(
                self._summary(
                    status="partial_failure",
                    files_scanned=len(planned),
                    changes=accepted,
                    files_changed=files_changed,
                    files_without_changes=files_without_changes,
                    skipped_changes=max(0, planned_change_count - accepted),
                    failed_file=exc.failed_file_id,
                    committed_file_ids=sorted(committed),
                )
            )
            _show_result_safely(
                show_result,
                status="partial_failure",
                files_scanned=len(planned),
                files_changed=files_changed,
                accepted_changes=accepted,
                skipped_changes=max(0, planned_change_count - accepted),
                files_not_written=max(0, len(planned) - files_changed),
                files_without_changes=files_without_changes,
                failed_file=exc.failed_file_id,
            )
            raise
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
        files_without_changes: int = 0,
        skipped_changes: int = 0,
        failed_file: Optional[str] = None,
        committed_file_ids: Optional[list[str]] = None,
    ) -> Dict[str, object]:
        summary: Dict[str, object] = {
            "plugin_version": PLUGIN_VERSION,
            "status": status,
            "state": self.session.state.value,
            "files_scanned": files_scanned,
            "files_changed": files_changed,
            "files_not_written": max(0, files_scanned - files_changed),
            "files_without_changes": max(0, files_without_changes),
            "changes": changes,
            "skipped_changes": skipped_changes,
        }
        if failed_file is not None:
            summary["failed_file"] = failed_file
        if committed_file_ids is not None:
            summary["committed_file_ids"] = committed_file_ids
        return summary


def _show_result_safely(show_result: Any, **values: object) -> None:
    """Keep headless/test hosts usable when Qt cannot show a result dialog."""

    try:
        show_result(**values)
    except Exception:
        # Result presentation is best effort after the write boundary has
        # completed; the structured session summary remains authoritative.
        return


def _book_supports_conversion(book: Any) -> bool:
    return callable(getattr(book, "text_iter", None)) and callable(
        getattr(book, "readfile", None)
    )


def _preferred_config(preferences: Dict[str, object], fallback: str) -> str:
    candidate = preferences.get("last_conversion_config", fallback)
    return candidate if isinstance(candidate, str) and candidate in SUPPORTED_CONFIGS else fallback


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
