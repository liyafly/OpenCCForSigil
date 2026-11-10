"""Top-level application controller."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path
from typing import Any

from app.errors import BookContainerSupportError, RuleConflictError, UserCancelled
from app.profiles import Profile
from app.session import Session, SessionState
from app.settings import RunSettings, profile_options, settings_hash, tokenizer_policy
from app.version import PLUGIN_VERSION
from core.models import ConvertRequest
from core.workflow import ConversionWorkflow, WorkflowCancelled, WorkflowCommitError
from logging_ext.logger import SessionLogger
from opencc_backend.backend import OpenCCBackend
from opencc_backend.configs import SUPPORTED_CONFIGS, is_jieba_config
from opencc_backend.errors import RuntimeSelectionError
from sigil.adapter import SigilBookAdapter
from sigil.storage import UserDataStore, resolve_user_data_dir
from transforms.language_tags import target_language
from ui.i18n import Translator, choose_language, rule_conflict_message


@dataclass
class _RunState:
    """Mutable state shared by the phases of one Controller._run_once call.

    The except/finally blocks of _run_once read the backend, adapter,
    documents and counters from here, so every phase assigns them as soon as
    they change rather than when the phase returns.
    """

    translator: Translator
    backend: OpenCCBackend | None = None
    adapter: SigilBookAdapter | None = None
    planned: Any = ()
    staged: Any = ()
    planned_change_count: int = 0
    files_without_changes: int = 0
    files_all_skipped: int = 0
    accepted_change_count: int = 0
    skipped_change_count: int = 0
    files_written: int = 0
    checkpoint_notice_shown: bool = False
    preferences: Any = None
    ui_preferences: Any = None
    language: str = "en"
    default_config: str = ""
    jieba_probe: Any = None
    settings: RunSettings | None = None
    targets: Any = None
    pending_config_choice: Any = None
    save_ui_preferences: Any = None
    show_result_with_preferences: Any = None
    # UI entry points, imported lazily once the backend self-test has passed.
    choose_scope: Any = None
    create_progress_reporter: Any = None
    show_preview: Any = None
    show_result: Any = None


@dataclass
class _Analysis:
    """One planning pass: the frozen choices, its workflow and the preview."""

    selected_config: str
    active_profile: Profile
    frozen_rules: Any
    language_tag: Any
    workflow: ConversionWorkflow
    invalid_source_diagnostics: tuple[Any, ...] = ()
    preview: Any = None


class Controller:
    """Coordinate one Sigil plugin invocation."""

    def __init__(self, bk: Any, data_dir: Path | None = None) -> None:
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
        run = _RunState(translator=Translator("en"))
        try:
            preference_recovery = self._preflight(run)
            recovery_notices = self._prepare_run_settings(run, preference_recovery)
            if not self._choose_initial_scope(run, recovery_notices):
                return 1
            analysis = self._analyze_until_previewed(run)
            if isinstance(analysis, int):
                return analysis
            self._stage_verify_commit(run, analysis)
            self._report_success(run, analysis)
            return 0
        except WorkflowCommitError as exc:
            self._report_commit_failure(run, exc)
            raise
        except UserCancelled:
            raise
        except Exception as exc:
            self._mark_session_failed()
            if self._report_partial_write_failure(run, exc):
                raise
            self._report_failure(run, exc)
            if isinstance(exc, RuntimeSelectionError):
                return 2
            raise
        finally:
            if run.backend is not None:
                run.backend.close()

    # -- preflight and run settings -------------------------------------------------

    def _preflight(self, run: _RunState) -> Any:
        """Load preferences, self-test the standard backend, then load the UI.

        Returns the storage recovery notice taken while loading preferences.
        """

        run.preferences = self.storage.load_preferences(
            default={
                "last_conversion_config": Profile().conversion,
                "ui": {},
            }
        )
        preflight_ui = run.preferences.get("ui")
        explicit_preflight_language = (
            preflight_ui.get("language") if isinstance(preflight_ui, dict) else None
        )
        run.translator.set_language(
            choose_language(
                explicit_preflight_language,
                getattr(self.bk, "sigil_ui_lang", None),
            )
        )

        preference_recovery = self.storage.take_recovery_notice()
        run.default_config = _preferred_config(run.preferences, Profile().conversion)
        self.session.transition(SessionState.SCANNING)
        # Always preflight the stable standard backend first. An optional
        # Jieba preference is resolved only after the selected payload has
        # advertised and verified the native plugin capability.
        run.backend = OpenCCBackend("s2t")
        self._run_backend_self_test(run.backend)
        run.jieba_probe = run.backend.start_jieba_probe(
            on_complete=lambda result: self.logger.event(
                "optional_jieba_probe",
                elapsed_ms=round(result[2], 1),
                result="available" if result[0] else "unavailable",
                reason=result[1],
            )
        ) or run.backend

        if not _book_supports_conversion(self.bk):
            raise BookContainerSupportError(
                "BookContainer must provide callable text_iter() and readfile() APIs"
            )

        # The UI is imported only after the backend self-test has passed.
        from ui.preview_window import (
            choose_scope,
            create_progress_reporter,
            show_result,
            show_preview,
        )

        run.choose_scope = choose_scope
        run.create_progress_reporter = create_progress_reporter
        run.show_result = show_result
        run.show_preview = show_preview
        return preference_recovery

    def _prepare_run_settings(self, run: _RunState, preference_recovery: Any) -> list[Any]:
        """Bind UI preferences, the book adapter and run settings.

        Returns the recovery notices the scope chooser should show.
        """

        raw_ui_preferences = run.preferences.get("ui")
        # Corrupt or legacy preference files must not make a conversion
        # crash while merging the UI namespace.  Preserve valid unknown UI
        # keys, but normalize every other value to an empty mapping.
        run.ui_preferences = (
            dict(raw_ui_preferences) if isinstance(raw_ui_preferences, dict) else {})
        run.save_ui_preferences = partial(self._save_run_ui_preferences, run)

        def show_result_with_preferences(**values):
            return run.show_result(
                **values,
                ui_preferences=run.ui_preferences,
                save_ui_preferences=run.save_ui_preferences,
            )

        run.show_result_with_preferences = show_result_with_preferences

        explicit_language = run.ui_preferences.get("language")
        host_language = getattr(self.bk, "sigil_ui_lang", None)
        run.language = choose_language(explicit_language, host_language)
        run.translator.set_language(run.language)

        run.adapter = SigilBookAdapter(self.bk)
        run.settings = RunSettings(
            self.storage, run.adapter, run.preferences, language=run.language,
            session_id=self.session.session_id,
        )
        run.settings.bind_run(run.settings.active, run.backend)
        run.settings.bind_ui_preferences(run.ui_preferences, run.save_ui_preferences)
        if run.settings.clear_profile_preference:
            self._update_preferences(run, {"profile_id": None})
        recovery_notices = []
        if preference_recovery:
            recovery_notices.append(preference_recovery)
        recovery_notices.extend(run.settings.take_recovery_notices())
        missing_rulesets = run.settings.take_missing_rulesets_notice()
        if missing_rulesets:
            recovery_notices.append(("rulesets_missing", ", ".join(missing_rulesets)))
        return recovery_notices

    def _update_preferences(self, run: _RunState, changes):
        run.preferences = self.storage.update_preferences(changes)
        return run.preferences

    def _save_run_ui_preferences(self, run: _RunState, values) -> None:
        run.ui_preferences = {**run.ui_preferences, **values}
        run.preferences = self._update_preferences(run, {"ui": values})
        saved_ui = run.preferences.get("ui")
        run.ui_preferences = (dict(saved_ui) if isinstance(saved_ui, dict)
                              else run.ui_preferences)

    # -- scope and configuration chooser --------------------------------------------

    def _merged_dialog_options(self, run: _RunState) -> dict[str, Any]:
        list_configs = getattr(run.jieba_probe, "available_configs_nonblocking", None)
        available_configs = (list_configs() if callable(list_configs)
                             else run.backend.available_configs_nonblocking())
        initial_options = profile_options(run.settings.active)
        previous = run.preferences.get("run_options")
        if isinstance(previous, dict):
            previous = dict(previous)
            if run.settings.active_profile_is_saved:
                previous.pop("ruleset_ids", None)
            initial_options.update(previous)
        return {
            "available_configs": available_configs,
            "default_config": run.default_config,
            "jieba_probe": run.jieba_probe,
            "initial_options": initial_options,
            "metadata_available": run.adapter.metadata_supported(),
            "services": run.settings,
        }

    def _open_scope_chooser(self, run: _RunState, **extra: Any) -> Any:
        """Show the merged scope/configuration chooser.

        ``extra`` carries the call-specific ``notice=`` or
        ``initial_selection=`` argument; it is passed only when given.
        """

        return run.choose_scope(
            run.adapter,
            initial_language=run.language,
            translator=run.translator,
            **extra,
            ui_preferences=run.ui_preferences,
            save_ui_preferences=run.save_ui_preferences,
            **self._merged_dialog_options(run),
        )

    def _apply_scope_outcome(self, run: _RunState, scope_outcome: Any) -> bool:
        """Adopt the chosen language and targets; record a cancelled run."""

        run.language = scope_outcome.language
        run.translator.set_language(run.language)
        run.settings.language = run.language
        if not scope_outcome.accepted or scope_outcome.selection is None:
            self._update_preferences(run, {"ui": {"language": run.language}})
            self.session.cancel()
            self.logger.summary(
                self._summary(status="cancelled", files_scanned=0, changes=0, files_changed=0)
            )
            return False
        run.targets = scope_outcome.selection
        return True

    def _choose_initial_scope(self, run: _RunState, recovery_notices: list[Any]) -> bool:
        # Text-capable hosts always get an explicit scope chooser.  A host
        # without selected_iter simply opens it with no initial checks; it
        # must never silently widen the run to ALL_XHTML.
        notice = {"notice": tuple(recovery_notices)} if recovery_notices else {}
        scope_outcome = self._open_scope_chooser(run, **notice)
        run.pending_config_choice = getattr(scope_outcome, "configuration", None)
        return self._apply_scope_outcome(run, scope_outcome)

    def _reselect_scope(self, run: _RunState, previous_selection: Any) -> bool:
        run.preferences = self.storage.load_preferences()
        run.default_config = _preferred_config(run.preferences, run.default_config)
        saved_ui = run.preferences.get("ui")
        run.ui_preferences = dict(saved_ui) if isinstance(saved_ui, dict) else {}
        run.settings.bind_ui_preferences(run.ui_preferences, run.save_ui_preferences)
        scope_outcome = self._open_scope_chooser(run, initial_selection=previous_selection)
        if not self._apply_scope_outcome(run, scope_outcome):
            return False
        run.pending_config_choice = getattr(scope_outcome, "configuration", None)
        return True

    # -- analysis and preview -------------------------------------------------------

    def _analyze_until_previewed(self, run: _RunState) -> _Analysis | int:
        """Plan and preview until the user accepts, or return an exit code."""

        # The merged chooser freezes direction and options with the target
        # selection, including on a first launch with no preference.
        while True:
            analysis = self._start_analysis(run)
            if not self._plan_documents(run, analysis):
                return 1
            if run.planned_change_count == 0:
                exit_code = self._finish_without_changes(run, analysis)
                if exit_code is None:
                    continue
                return exit_code

            self.session.transition(SessionState.PREVIEWING)
            preview = analysis.preview = run.show_preview(
                run.planned,
                translator=run.translator,
                services=run.settings,
                ui_preferences=run.ui_preferences,
                save_ui_preferences=run.save_ui_preferences,
            )
            run.files_all_skipped = _count_files_all_skipped(
                run.planned, getattr(preview, "previews", ()))
            if getattr(preview, "back_to_settings", False):
                run.default_config = analysis.selected_config
                run.settings.bind_run(analysis.active_profile, run.backend)
                if not self._reselect_scope(run, run.targets):
                    return 1
                self.session.transition(SessionState.SCANNING)
                continue
            if not preview.accepted:
                self.session.cancel()
                self.logger.summary(
                    self._summary(
                        status="cancelled",
                        files_scanned=len(run.planned),
                        changes=run.planned_change_count,
                        files_changed=0,
                        files_without_changes=run.files_without_changes,
                    )
                )
                _show_result_safely(
                    run.show_result_with_preferences, translator=run.translator,
                    status="cancelled",
                    files_scanned=len(run.planned),
                    files_changed=0,
                    accepted_changes=0,
                    skipped_changes=0,
                    files_not_written=len(run.planned),
                    files_without_changes=run.files_without_changes,
                    files_all_skipped=run.files_all_skipped,
                )
                return 1

            return analysis

    def _start_analysis(self, run: _RunState) -> _Analysis:
        """Freeze the chosen configuration, profile and rules into a workflow."""

        selected_config = run.pending_config_choice
        run.pending_config_choice = None
        assert selected_config is not None
        options = dict(getattr(selected_config, "options", {}))
        preference_options = dict(getattr(
            selected_config, "preference_options", options))
        selected_config = str(selected_config)
        language_tag = target_language(
            selected_config, options.get("language_metadata", "keep"),
            options.get("language_preset", "legacy"), options.get("language_region", ""),
        )
        run.targets = replace(run.targets, include_ncx=options.get("include_ncx", False),
                              include_metadata=options.get("include_metadata", False),
                              update_language=bool(language_tag))
        settings = run.settings
        active_profile = settings.current_profile(selected_config, options)
        frozen_rules = settings.freeze_rules(active_profile)
        profile_preference = (
            run.preferences.get("profile_id") if settings.preserve_profile_preference
            else active_profile.id if (
                settings.profiles.directory / f"{active_profile.id}.json").exists()
            else None
        )
        self._update_preferences(run, {
            "profile_id": profile_preference,
            "last_conversion_config": selected_config,
            "run_options": preference_options,
            "ui": {"language": run.language},
        })
        if selected_config != run.backend.config:
            run.backend.close()
            run.backend = OpenCCBackend(selected_config, jieba_probe=run.jieba_probe)
            self._run_backend_self_test(run.backend)

        settings.language = run.language
        settings.bind_run(active_profile, run.backend)
        self.session.metadata.update(config=selected_config, profile_id=active_profile.id,
                                     profile_hash=settings_hash(active_profile),
                                     rules_hash=frozen_rules.rules_hash)
        self.session.transition(SessionState.ANALYZING)
        workflow = ConversionWorkflow(
            run.adapter,
            run.backend,
            ConvertRequest(
                selected_config,
                segmentation="jieba" if is_jieba_config(selected_config) else "mmseg",
                language_tag=language_tag,
                rules_snapshot=frozen_rules,
                quotation_mode=active_profile.quotation_mode,
                punctuation_mode=active_profile.punctuation_mode,
                pivot_chain=active_profile.pivot_chain if active_profile.force_pivot else (),
                profile_id=active_profile.id,
                book_fingerprint=(settings.book_fingerprint if
                    any(rule.scope == "book" for rule in frozen_rules.rules) else ""),
            ),
            scope=run.targets.scope,
            targets=run.targets,
            tokenizer_options=tokenizer_policy(active_profile),
            session_id=self.session.session_id,
            profile_id=active_profile.id,
            snapshot_guard=settings.snapshot_guard(),
        )
        return _Analysis(selected_config, active_profile, frozen_rules, language_tag, workflow)

    def _plan_documents(self, run: _RunState, analysis: _Analysis) -> bool:
        """Plan the targets in the worker; False when the user cancelled."""

        progress = run.create_progress_reporter(
            len(run.targets.file_ids), translator=run.translator,
            ui_preferences=run.ui_preferences,
            save_ui_preferences=run.save_ui_preferences,
        )
        try:
            run.planned = analysis.workflow.plan_in_worker(
                lambda config: OpenCCBackend(config, jieba_probe=run.jieba_probe),
                progress=progress.update,
                cancelled=progress.cancelled,
            )
        except WorkflowCancelled:
            self.session.cancel()
            self.logger.summary(
                self._summary(status="cancelled", files_scanned=0, changes=0, files_changed=0)
            )
            _show_result_safely(
                run.show_result_with_preferences, translator=run.translator,
                status="cancelled",
                files_scanned=0,
                files_changed=0,
                accepted_changes=0,
                skipped_changes=0,
            )
            return False
        finally:
            progress.close()
        planned = run.planned
        run.planned_change_count = sum(len(item.plan.changes) for item in planned)
        run.files_without_changes = sum(not item.plan.changes for item in planned)
        run.files_all_skipped = 0
        self.logger.event(
            "plan_built",
            profile_id=analysis.active_profile.id,
            profile_hash=settings_hash(analysis.active_profile),
            rules_hash=analysis.frozen_rules.rules_hash,
            config=analysis.selected_config,
            files_scanned=len(planned),
            changes=run.planned_change_count,
            document_counts={kind: sum(item.source.document_kind == kind for item in planned)
                             for kind in ("xhtml", "nav", "ncx", "metadata")},
            language_tag=analysis.language_tag,
        )
        self.session.transition(SessionState.PLANNED)

        analysis.invalid_source_diagnostics = tuple(
            (item.source.href, diagnostic.code, diagnostic.message)
            for item in planned
            for diagnostic in item.plan.diagnostics
            if diagnostic.code == "SOURCE_INVALID_XHTML"
        )
        return True

    def _finish_without_changes(self, run: _RunState, analysis: _Analysis) -> int | None:
        """Report a run with no proposed changes.

        Returns None when the user went back to the scope chooser and picked a
        new selection, otherwise the run's exit code.
        """

        self.session.transition(SessionState.PREVIEWING)
        self.session.metadata["checkpoint_notice_shown"] = run.checkpoint_notice_shown
        result_action = _show_result_safely(
            run.show_result_with_preferences, translator=run.translator,
            status="success",
            files_scanned=len(run.planned),
            files_changed=0,
            accepted_changes=0,
            skipped_changes=0,
            files_not_written=len(run.planned),
            files_without_changes=run.files_without_changes,
            return_to_scope=True,
            diagnostics=analysis.invalid_source_diagnostics,
            diagnostic_documents=run.planned,
        )
        if result_action == "back_to_scope":
            if not self._reselect_scope(run, run.targets):
                return 1
            self.session.transition(SessionState.SCANNING)
            return None
        workflow = analysis.workflow
        finalized = workflow.finalize(workflow.preview())
        self.session.transition(SessionState.APPLYING_TO_STAGE)
        run.staged = workflow.stage(finalized)
        self.session.transition(SessionState.VERIFYING)
        workflow.verify(run.staged)
        self.session.transition(SessionState.COMMITTING)
        workflow.commit(run.staged)
        self.session.complete()
        self.logger.summary(self._summary(
            status="success",
            files_scanned=len(run.planned),
            changes=0,
            files_changed=0,
            files_without_changes=run.files_without_changes,
        ))
        self._record_history(run.planned, run.staged, run.backend)
        return 0

    # -- stage, verify, commit and report -------------------------------------------

    def _stage_verify_commit(self, run: _RunState, analysis: _Analysis) -> None:
        preview = analysis.preview
        workflow = analysis.workflow
        self.session.metadata["checkpoint_notice_shown"] = bool(
            run.checkpoint_notice_shown or getattr(preview, "checkpoint_notice_shown", False))
        finalized = workflow.finalize(preview.previews)
        run.accepted_change_count = sum(len(plan.changes) for _, plan in finalized)
        run.skipped_change_count = run.planned_change_count - run.accepted_change_count
        self.logger.event(
            "preview_completed",
            accepted_changes=run.accepted_change_count,
            planned_changes=run.planned_change_count,
        )

        self.session.transition(SessionState.APPLYING_TO_STAGE)
        post_preview_progress = run.create_progress_reporter(
            len(run.planned), translator=run.translator,
            ui_preferences=run.ui_preferences,
            save_ui_preferences=run.save_ui_preferences,
        )
        commit_succeeded = False
        try:
            # Staging and verification happen before the write boundary;
            # keep the user informed without offering a cancellation
            # action that cannot safely interrupt these phases.
            disable_cancel = getattr(post_preview_progress, "disable_cancel", None)
            if callable(disable_cancel):
                disable_cancel()
            run.staged = workflow.stage(
                finalized,
                progress=post_preview_progress.update,
            )
            self.session.transition(SessionState.VERIFYING)
            verification = workflow.verify(
                run.staged,
                progress=post_preview_progress.update,
            )
            self.logger.event(
                "verification_completed",
                files_verified=len(verification),
                passed=all(result.passed for result in verification),
            )
            self.session.transition(SessionState.COMMITTING)
            workflow.commit(
                run.staged,
                progress=post_preview_progress.update,
                on_progress_failure=lambda phase, index, total, href, error: self.logger.event(
                    "progress_failed",
                    level="ERROR",
                    phase=phase,
                    index=index,
                    total=total,
                    href=href,
                    error_type=type(error).__name__,
                    error=str(error),
                ),
            )
            commit_succeeded = True
        finally:
            if commit_succeeded:
                self.session.complete()
                self._best_effort("progress_close", post_preview_progress.close)
            else:
                post_preview_progress.close()
        run.files_written = len(run.staged)

    def _report_success(self, run: _RunState, analysis: _Analysis) -> None:
        """Post-commit bookkeeping; nothing here may undo the completed write."""

        self._best_effort(
            "commit_completed",
            lambda: self.logger.event(
                "commit_completed",
                files_changed=len(run.staged),
                changes=run.accepted_change_count,
            ),
        )
        self._best_effort(
            "summary",
            lambda: self.logger.summary(
                self._summary(
                    status="success",
                    files_scanned=len(run.planned),
                    changes=run.accepted_change_count,
                    files_changed=len(run.staged),
                    files_without_changes=run.files_without_changes,
                    skipped_changes=run.skipped_change_count,
                )
            ),
        )
        report_text = self._best_effort(
            "history", lambda: self._record_history(run.planned, run.staged, run.backend),
            default=None,
        )
        _show_result_safely(
            run.show_result_with_preferences, translator=run.translator,
            status="success",
            files_scanned=len(run.planned),
            files_changed=len(run.staged),
            accepted_changes=run.accepted_change_count,
            skipped_changes=run.skipped_change_count,
            files_not_written=max(0, len(run.planned) - len(run.staged)),
            files_without_changes=run.files_without_changes,
            files_all_skipped=run.files_all_skipped,
            diagnostics=analysis.invalid_source_diagnostics,
            report_text=report_text,
        )

    # -- failure reporting (called from _run_once's except blocks) -------------------

    def _mark_session_failed(self) -> None:
        if self.session.state not in {
            SessionState.COMPLETED,
            SessionState.CANCELLED,
            SessionState.FAILED,
        }:
            self.session.transition(SessionState.FAILED)

    def _report_commit_failure(self, run: _RunState, exc: WorkflowCommitError) -> None:
        self._mark_session_failed()
        committed = set(exc.committed_file_ids)
        files_changed = len(committed)
        accepted = sum(
            len(item.plan.changes) for item in run.staged if item.file_id in committed
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
                files_scanned=len(run.planned),
                changes=accepted,
                files_changed=files_changed,
                files_without_changes=run.files_without_changes,
                skipped_changes=max(0, run.planned_change_count - accepted),
                failed_file=exc.failed_file_id,
                committed_file_ids=sorted(committed),
            )
        )
        _show_result_safely(
            run.show_result_with_preferences, translator=run.translator,
            status="partial_failure",
            files_scanned=len(run.planned),
            files_changed=files_changed,
            accepted_changes=accepted,
            skipped_changes=max(0, run.planned_change_count - accepted),
            files_not_written=max(0, len(run.planned) - files_changed),
            files_without_changes=run.files_without_changes,
            files_all_skipped=run.files_all_skipped,
            failed_file=exc.failed_file_id,
        )

    def _report_partial_write_failure(self, run: _RunState, exc: Exception) -> bool:
        """Report a failure after some files were written; False if none were."""

        committed = set(run.adapter.committed_file_ids if run.adapter is not None else ())
        if not committed:
            return False
        run.files_written = len(committed)
        accepted = sum(
            len(item.plan.changes) for item in run.staged if item.file_id in committed
        )
        self.logger.exception("controller_failed_after_write", exc)
        self.logger.event(
            "commit_partial_failure",
            committed_file_ids=sorted(committed),
            failed_file_id=getattr(exc, "failed_file_id", None),
        )
        self.logger.summary(
            self._summary(
                status="partial_failure",
                files_scanned=len(run.planned),
                changes=accepted,
                files_changed=run.files_written,
                files_without_changes=run.files_without_changes,
                skipped_changes=max(0, run.planned_change_count - accepted),
                committed_file_ids=sorted(committed),
            )
        )
        _show_result_safely(
            run.show_result_with_preferences,
            translator=run.translator,
            status="partial_failure",
            files_scanned=len(run.planned),
            files_changed=run.files_written,
            accepted_changes=accepted,
            skipped_changes=max(0, run.planned_change_count - accepted),
            files_not_written=max(0, len(run.planned) - run.files_written),
            files_without_changes=run.files_without_changes,
            files_all_skipped=run.files_all_skipped,
            failed_file=getattr(exc, "failed_file_id", None),
        )
        return True

    def _report_failure(self, run: _RunState, exc: Exception) -> None:
        self.logger.exception("controller_failed")
        self.logger.summary(
            self._summary(status="failed", files_scanned=0, changes=0, files_changed=0)
        )
        href_by_id = {item.source.file_id: item.source.href for item in run.planned}
        affected_files = tuple(
            (href_by_id.get(str(href), str(href)), tuple(codes))
            for href, codes in getattr(exc, "affected_files", ())
        )
        error_values = {
            "translator": run.translator,
            "kind": _error_kind(exc),
            "detail": type(exc).__name__,
            "files_written": run.files_written,
            "log_path": str(self.logger.log_path),
            "affected_files": affected_files,
        }
        if isinstance(exc, RuleConflictError):
            error_values["summary"] = _rule_conflict_summary(exc, run.translator)
        if isinstance(exc, BookContainerSupportError):
            error_values["summary"] = run.translator.text("error.book_api_unavailable")
        if isinstance(exc, RuntimeSelectionError):
            error_values["summary"] = _runtime_selection_summary(exc, run.translator)
        _show_error_safely(
            self.logger,
            **error_values,
        )

    def _run_backend_self_test(self, backend: OpenCCBackend) -> None:
        self_test = backend.self_test(include_optional=False)
        self.logger.event(
            "backend_self_test",
            passed=self_test.passed,
            checks=self_test.checks,
            provenance=backend.provenance().as_dict(),
        )
        if not self_test.passed:
            raise RuntimeError(self_test.error or "official OpenCC backend self-test failed")

    def _best_effort(self, label, action, default=None):
        """Run post-commit bookkeeping without undoing a completed write."""

        try:
            return action()
        except Exception as error:
            try:
                self.logger.exception(f"post_commit_{label}_failed", error)
            except Exception:
                print(
                    f"OpenCCForSigil: {label} failed after commit: {error}",
                    file=sys.stderr,
                )
            return default

    def _record_history(self, planned, staged, backend):
        from core.staging import source_sha256
        from logging_ext.history import HistoryStore
        from logging_ext.report import render_markdown
        by_id = {item.source.file_id: item for item in planned}
        manifest = {
            "schema_version": 1, "session_id": self.session.session_id,
            "files": [{
                "id": item.file_id, "href": by_id[item.file_id].source.href,
                "before_sha256": source_sha256(item.original),
                "after_sha256": source_sha256(item.converted),
                "bytes_before": len(item.original.encode("utf-8")),
                "bytes_after": len(item.converted.encode("utf-8")),
                "change_count": len(item.plan.changes),
                "high_risk_changes": sum(change.risk == "HIGH" for change in item.plan.changes),
                "warnings": [diagnostic.code for diagnostic in item.plan.diagnostics],
            } for item in staged],
        }
        report_text = None
        try:
            summary = json.loads(self.logger.summary_path.read_text(encoding="utf-8"))
            book_path = ""
            get_book_path = getattr(self.bk, "get_epub_filepath", None)
            if callable(get_book_path):
                try:
                    raw_path = get_book_path()
                    if raw_path:
                        book_path = Path(str(raw_path)).name
                except Exception:
                    book_path = ""
            summary["book_label"] = book_path
            provenance = backend.provenance().as_dict()
            report_text = render_markdown(summary, manifest, provenance)
            HistoryStore(self.storage.paths.history).record_session(
                summary, manifest, provenance)
            self.logger.event("commit_manifest", **manifest)
        except (OSError, ValueError) as exc:
            # A failed audit export after the write boundary must not pretend
            # that the verified conversion itself failed or was rolled back.
            self.logger.event("history_failed", level="ERROR", error=str(exc))
            print(f"Conversion completed, but history could not be saved: {exc}")
        return report_text

    def _summary(
        self,
        *,
        status: str,
        files_scanned: int,
        changes: int,
        files_changed: int,
        files_without_changes: int = 0,
        skipped_changes: int = 0,
        failed_file: str | None = None,
        committed_file_ids: list[str] | None = None,
    ) -> dict[str, object]:
        summary: dict[str, object] = {
            "plugin_version": PLUGIN_VERSION,
            "session_id": self.session.session_id,
            **self.session.metadata,
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


def _count_files_all_skipped(planned, previews) -> int:
    """Count documents whose proposed changes were all explicitly rejected."""

    if previews is None or len(planned) != len(previews):
        return 0
    count = 0
    for item, preview in zip(planned, previews):
        total = len(item.plan.changes)
        if total <= 0:
            continue
        summary = preview.summary()
        if summary.get("accepted", 0) == 0 and summary.get("rejected", 0) == total:
            count += 1
    return count


def _show_result_safely(
    show_result: Any, *, translator: Translator | None = None, **values: object,
) -> Any:
    """Keep headless/test hosts usable when Qt cannot show a result dialog."""

    try:
        return show_result(**values, translator=translator)
    except Exception:
        # Result presentation is best effort after the write boundary has
        # completed; the structured session summary remains authoritative.
        return None


def _book_supports_conversion(book: Any) -> bool:
    return callable(getattr(book, "text_iter", None)) and callable(
        getattr(book, "readfile", None)
    )


def _error_kind(error: BaseException) -> str:
    code = getattr(error, "code", None)
    if isinstance(code, str) and code:
        return code
    if "profiles or rules changed after preview" in str(error):
        return "SETTINGS_CHANGED"
    return "UNEXPECTED_ERROR"


def _rule_conflict_summary(error: RuleConflictError, translator: Translator) -> str:
    return rule_conflict_message(translator, error)


def _runtime_selection_summary(error: RuntimeSelectionError, translator: Translator) -> str:
    detected = error.detected
    runtime_label = (
        f"{detected.get('os', 'unknown')}/{detected.get('architecture', 'unknown')}, "
        f"{detected.get('implementation', 'Python')} "
        f"{detected.get('python_version', 'unknown')} ({detected.get('abi', 'unknown')})"
    )
    if error.reason == "no_payload_in_package":
        asset_suffix = {
            ("linux", "aarch64"): "linux-aarch64",
            ("linux", "x86_64"): "linux-x86_64",
            ("macos", "arm64"): "macos-arm64",
            ("macos", "x86_64"): "macos-x86_64",
            ("windows", "x86_64"): "windows-x86_64",
        }.get((detected.get("os", ""), detected.get("architecture", "")))
        recommended_asset = (
            f"OpenCCForSigil_{PLUGIN_VERSION}_{asset_suffix}.zip"
            if asset_suffix
            else f"OpenCCForSigil_{PLUGIN_VERSION}.zip"
        )
        return translator.text(
            "error.runtime_no_payload",
            package_runtimes=", ".join(error.package_runtimes) or "(none)",
            detected=runtime_label,
            recommended_asset=recommended_asset,
            fat_asset=f"OpenCCForSigil_{PLUGIN_VERSION}.zip",
        )
    if error.reason == "unsupported_platform":
        if detected.get("os") == "windows" and detected.get("architecture") in {
            "arm64",
            "aarch64",
        }:
            reason = translator.text("error.runtime_reason_windows_arm64")
        else:
            reason = translator.text("error.runtime_reason_unverified")
        return translator.text(
            "error.runtime_unsupported_platform",
            detected=runtime_label,
            reason=reason,
        )
    key = (
        "error.runtime_python_version_linux"
        if detected.get("os") == "linux"
        else "error.runtime_python_version"
    )
    return translator.text(key, detected=runtime_label)


def _show_error_safely(logger: SessionLogger, **values: object) -> None:
    """Show a user-facing error without replacing the original exception."""

    try:
        from ui.preview_window import show_error

        show_error(**values)
    except Exception as error:
        logger.event("error_dialog_unavailable", level="ERROR",
                     error_type=type(error).__name__)


def _preferred_config(preferences: dict[str, object], fallback: str) -> str:
    candidate = preferences.get("last_conversion_config", fallback)
    return candidate if isinstance(candidate, str) and candidate in SUPPORTED_CONFIGS else fallback
