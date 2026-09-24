"""Top-level application controller."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, Optional

from app.errors import UserCancelled
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
from ui.i18n import Translator, choose_language


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
        adapter: Optional[SigilBookAdapter] = None
        planned = ()
        staged = ()
        planned_change_count = 0
        files_without_changes = 0
        accepted_change_count = 0
        skipped_change_count = 0
        files_written = 0
        translator = Translator("en")
        try:
            profile = _load_conservative_profile()
            preferences = self.storage.load_preferences(
                default={
                    "last_conversion_config": str(profile["conversion"]),
                    "ui": {},
                }
            )
            preflight_ui = preferences.get("ui")
            explicit_preflight_language = (
                preflight_ui.get("language") if isinstance(preflight_ui, dict) else None
            )
            translator.set_language(
                choose_language(
                    explicit_preflight_language,
                    getattr(self.bk, "sigil_ui_lang", None),
                )
            )

            def update_preferences(changes):
                nonlocal preferences
                preferences = self.storage.update_preferences(changes)
                return preferences

            preference_recovery = self.storage.take_recovery_notice()
            default_config = _preferred_config(preferences, str(profile["conversion"]))
            self.session.transition(SessionState.SCANNING)
            # Always preflight the stable standard backend first. An optional
            # Jieba preference is resolved only after the selected payload has
            # advertised and verified the native plugin capability.
            backend = OpenCCBackend("s2t")
            self._run_backend_self_test(backend)
            jieba_probe = backend.start_jieba_probe(
                on_complete=lambda result: self.logger.event(
                    "optional_jieba_probe",
                    elapsed_ms=round(result[2], 1),
                    result="available" if result[0] else "unavailable",
                    reason=result[1],
                )
            ) or backend

            if not _book_supports_conversion(self.bk):
                return self._complete_noop(
                    message="BookContainer text API unavailable; preflight-only run",
                )

            from ui.preview_window import (
                choose_conversion_config,
                choose_scope,
                create_progress_reporter,
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
            translator.set_language(language)

            adapter = SigilBookAdapter(self.bk)
            settings = RunSettings(
                self.storage, adapter, preferences, language=language,
                session_id=self.session.session_id,
            )
            settings.bind_run(settings.active, backend)
            if settings.clear_profile_preference:
                update_preferences({"profile_id": None})
            recovery_notices = []
            if preference_recovery:
                recovery_notices.append(preference_recovery)
            recovery_notices.extend(settings.take_recovery_notices())
            missing_rulesets = settings.take_missing_rulesets_notice()
            if missing_rulesets:
                recovery_notices.append(("rulesets_missing", ", ".join(missing_rulesets)))
            checkpoint_notice_enabled = settings.checkpoint_notice_enabled()
            # Text-capable hosts always get an explicit scope chooser.  A host
            # without selected_iter simply opens it with no initial checks; it
            # must never silently widen the run to ALL_XHTML.
            if recovery_notices:
                scope_outcome = choose_scope(
                    adapter,
                    initial_language=language,
                    translator=translator,
                    notice=tuple(recovery_notices),
                    checkpoint_notice_enabled=checkpoint_notice_enabled,
                    hide_checkpoint_notice=settings.hide_checkpoint_notice,
                )
            else:
                scope_outcome = choose_scope(
                    adapter,
                    initial_language=language,
                    translator=translator,
                    checkpoint_notice_enabled=checkpoint_notice_enabled,
                    hide_checkpoint_notice=settings.hide_checkpoint_notice,
                )
            checkpoint_notice_shown = bool(scope_outcome.checkpoint_notice_shown)
            language = scope_outcome.language
            translator.set_language(language)
            settings.language = language
            if not scope_outcome.accepted or scope_outcome.selection is None:
                update_preferences({"ui": {"language": language}})
                self.session.cancel()
                self.logger.summary(
                    self._summary(status="cancelled", files_scanned=0, changes=0, files_changed=0)
                )
                return 1
            targets = scope_outcome.selection

            def reselect_scope(previous_selection):
                nonlocal language, preferences, ui_preferences, targets
                nonlocal default_config
                nonlocal checkpoint_notice_shown
                preferences = self.storage.load_preferences()
                default_config = _preferred_config(preferences, default_config)
                saved_ui = preferences.get("ui")
                ui_preferences = dict(saved_ui) if isinstance(saved_ui, dict) else {}
                scope_outcome = choose_scope(
                    adapter,
                    initial_language=language,
                    translator=translator,
                    initial_selection=previous_selection,
                    checkpoint_notice_enabled=False,
                )
                checkpoint_notice_shown = (
                    checkpoint_notice_shown or scope_outcome.checkpoint_notice_shown)
                language = scope_outcome.language
                translator.set_language(language)
                settings.language = language
                if not scope_outcome.accepted or scope_outcome.selection is None:
                    update_preferences({"ui": {"language": language}})
                    self.session.cancel()
                    self.logger.summary(self._summary(
                        status="cancelled", files_scanned=0, changes=0, files_changed=0))
                    return False
                targets = scope_outcome.selection
                return True

            # The language choice is now settled before the direction dialog
            # is constructed, including on a first launch with no preference.
            while True:
                list_configs = getattr(jieba_probe, "available_configs_nonblocking", None)
                available_configs = (
                    list_configs() if callable(list_configs)
                    else backend.available_configs_nonblocking()
                )
                initial_options = profile_options(settings.active)
                previous_options = preferences.get("run_options")
                if isinstance(previous_options, dict):
                    previous_options = dict(previous_options)
                    if settings.active_profile_is_saved:
                        previous_options.pop("ruleset_ids", None)
                    initial_options.update(previous_options)

                def save_run_ui_preferences(values):
                    nonlocal preferences, ui_preferences
                    ui_preferences = {**ui_preferences, **values}
                    preferences = update_preferences({"ui": values})
                    saved_ui = preferences.get("ui")
                    ui_preferences = (dict(saved_ui) if isinstance(saved_ui, dict)
                                      else ui_preferences)

                selected_config = choose_conversion_config(
                    available_configs,
                    default_config=default_config,
                    jieba_probe=jieba_probe,
                    initial_options=initial_options,
                    metadata_available=adapter.metadata_supported(),
                    nav_available=bool(
                        adapter.nav_id() and adapter.nav_id() in targets.file_ids),
                    services=settings,
                    ui_preferences=ui_preferences,
                    save_ui_preferences=save_run_ui_preferences,
                    translator=translator,
                )
                action = getattr(selected_config, "action", None)
                if action == "back_to_scope":
                    current_choice = getattr(selected_config, "configuration", None)
                    if current_choice is not None:
                        choice_options = dict(getattr(
                            current_choice, "preference_options",
                            getattr(current_choice, "options", {}),
                        ))
                        update_preferences({
                            "last_conversion_config": str(current_choice),
                            "run_options": choice_options,
                        })
                    if not reselect_scope(targets):
                        return 1
                    continue
                if action == "cancel" or selected_config is None:
                    update_preferences({"ui": {"language": language}})
                    self.session.cancel()
                    self.logger.summary(
                        self._summary(status="cancelled", files_scanned=0, changes=0, files_changed=0)
                    )
                    return 1
                if action == "continue":
                    selected_config = selected_config.configuration
                options = dict(getattr(selected_config, "options", {}))
                preference_options = dict(getattr(
                    selected_config, "preference_options", options))
                selected_config = str(selected_config)
                language_tag = target_language(
                    selected_config, options.get("language_metadata", "keep"),
                    options.get("language_preset", "legacy"), options.get("language_region", ""),
                )
                targets = replace(targets, include_nav=options.get("include_nav", True),
                                  include_ncx=options.get("include_ncx", False),
                                  include_metadata=options.get("include_metadata", False),
                                  update_language=bool(language_tag))
                active_profile = settings.current_profile(selected_config, options)
                frozen_rules = settings.freeze_rules(active_profile)
                profile_preference = (
                    preferences.get("profile_id") if settings.preserve_profile_preference
                    else active_profile.id if (
                        settings.profiles.directory / f"{active_profile.id}.json").exists()
                    else None
                )
                update_preferences({
                    "profile_id": profile_preference,
                    "last_conversion_config": selected_config,
                    "run_options": preference_options,
                    "ui": {"language": language},
                })
                if selected_config != backend.config:
                    backend.close()
                    backend = OpenCCBackend(selected_config, jieba_probe=jieba_probe)
                    self._run_backend_self_test(backend)

                settings.language = language
                settings.bind_run(active_profile, backend)
                self.session.metadata.update(config=selected_config, profile_id=active_profile.id,
                                             profile_hash=settings_hash(active_profile),
                                             rules_hash=frozen_rules.rules_hash)
                self.session.transition(SessionState.ANALYZING)
                workflow = ConversionWorkflow(
                    adapter,
                    backend,
                    ConvertRequest(
                        selected_config,
                        segmentation="jieba" if is_jieba_config(selected_config) else "mmseg",
                        language_tag=language_tag,
                        rules_snapshot=frozen_rules,
                        quotation_mode=active_profile.quotation_mode,
                        punctuation_mode=active_profile.punctuation_mode,
                        pivot_chain=active_profile.pivot_chain if active_profile.force_pivot else (),
                        detailed_classification=bool(options.get("detailed_classification", True)),
                        diagnose_mixed=bool(options.get("diagnose_mixed", True)),
                        profile_id=active_profile.id,
                        book_fingerprint=(settings.book_fingerprint if
                            any(rule.scope == "book" for rule in frozen_rules.rules) else ""),
                    ),
                    scope=targets.scope,
                    targets=targets,
                    tokenizer_options=tokenizer_policy(active_profile),
                    session_id=self.session.session_id,
                    profile_id=active_profile.id,
                    snapshot_guard=settings.snapshot_guard(),
                )
                progress = create_progress_reporter(len(targets.file_ids), translator=translator)
                try:
                    planned = workflow.plan_in_worker(
                        OpenCCBackend,
                        progress=progress.update,
                        cancelled=progress.cancelled,
                    )
                except WorkflowCancelled:
                    self.session.cancel()
                    self.logger.summary(
                        self._summary(status="cancelled", files_scanned=0, changes=0, files_changed=0)
                    )
                    _show_result_safely(
                        show_result, translator=translator,
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
                    profile_id=active_profile.id,
                    profile_hash=settings_hash(active_profile),
                    rules_hash=frozen_rules.rules_hash,
                    config=selected_config,
                    files_scanned=len(planned),
                    changes=planned_change_count,
                    document_counts={kind: sum(item.source.document_kind == kind for item in planned)
                                     for kind in ("xhtml", "nav", "ncx", "metadata")},
                    language_tag=language_tag,
                )
                self.session.transition(SessionState.PLANNED)

                invalid_source_diagnostics = tuple(
                    (item.source.href, diagnostic.code, diagnostic.message)
                    for item in planned
                    for diagnostic in item.plan.diagnostics
                    if diagnostic.code == "SOURCE_INVALID_XHTML"
                )
                if planned_change_count == 0:
                    self.session.transition(SessionState.PREVIEWING)
                    self.session.metadata["checkpoint_notice_shown"] = checkpoint_notice_shown
                    result_action = _show_result_safely(
                        show_result, translator=translator,
                        status="success",
                        files_scanned=len(planned),
                        files_changed=0,
                        accepted_changes=0,
                        skipped_changes=0,
                        files_not_written=len(planned),
                        files_without_changes=files_without_changes,
                        return_to_scope=True,
                        diagnostics=invalid_source_diagnostics,
                    )
                    if result_action == "back_to_scope":
                        if not reselect_scope(targets):
                            return 1
                        self.session.transition(SessionState.SCANNING)
                        continue
                    finalized = workflow.finalize(workflow.preview())
                    self.session.transition(SessionState.APPLYING_TO_STAGE)
                    staged = workflow.stage(finalized)
                    self.session.transition(SessionState.VERIFYING)
                    workflow.verify(staged)
                    self.session.transition(SessionState.COMMITTING)
                    workflow.commit(staged)
                    self.session.complete()
                    self.logger.summary(self._summary(
                        status="success",
                        files_scanned=len(planned),
                        changes=0,
                        files_changed=0,
                        files_without_changes=files_without_changes,
                    ))
                    self._record_history(planned, staged, backend)
                    return 0

                self.session.transition(SessionState.PREVIEWING)
                preview = show_preview(planned, translator=translator, services=settings)
                if getattr(preview, "back_to_settings", False):
                    default_config = selected_config
                    settings.bind_run(active_profile, backend)
                    if not reselect_scope(targets):
                        return 1
                    self.session.transition(SessionState.SCANNING)
                    continue
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
                    _show_result_safely(
                        show_result, translator=translator,
                        status="cancelled",
                        files_scanned=len(planned),
                        files_changed=0,
                        accepted_changes=0,
                        skipped_changes=0,
                        files_not_written=len(planned),
                        files_without_changes=files_without_changes,
                    )
                    return 1

                break

            self.session.metadata["checkpoint_notice_shown"] = bool(
                checkpoint_notice_shown or getattr(preview, "checkpoint_notice_shown", False))
            finalized = workflow.finalize(preview.previews)
            accepted_change_count = sum(len(plan.changes) for _, plan in finalized)
            skipped_change_count = planned_change_count - accepted_change_count
            self.logger.event(
                "preview_completed",
                accepted_changes=accepted_change_count,
                planned_changes=planned_change_count,
            )

            self.session.transition(SessionState.APPLYING_TO_STAGE)
            post_preview_progress = create_progress_reporter(len(planned), translator=translator)
            commit_succeeded = False
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
                self.logger.event(
                    "verification_completed",
                    files_verified=len(verification),
                    passed=all(result.passed for result in verification),
                )
                self.session.transition(SessionState.COMMITTING)
                workflow.commit(
                    staged,
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
            files_written = len(staged)
            self._best_effort(
                "commit_completed",
                lambda: self.logger.event(
                    "commit_completed",
                    files_changed=len(staged),
                    changes=accepted_change_count,
                ),
            )
            self._best_effort(
                "summary",
                lambda: self.logger.summary(
                    self._summary(
                        status="success",
                        files_scanned=len(planned),
                        changes=accepted_change_count,
                        files_changed=len(staged),
                        files_without_changes=files_without_changes,
                        skipped_changes=skipped_change_count,
                    )
                ),
            )
            report_text = self._best_effort(
                "history", lambda: self._record_history(planned, staged, backend), default=None
            )
            _show_result_safely(
                show_result, translator=translator,
                status="success",
                files_scanned=len(planned),
                files_changed=len(staged),
                accepted_changes=accepted_change_count,
                skipped_changes=skipped_change_count,
                files_not_written=max(0, len(planned) - len(staged)),
                files_without_changes=files_without_changes,
                diagnostics=invalid_source_diagnostics,
                report_text=report_text,
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
                show_result, translator=translator,
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
        except UserCancelled:
            raise
        except Exception as exc:
            if self.session.state not in {
                SessionState.COMPLETED,
                SessionState.CANCELLED,
                SessionState.FAILED,
            }:
                self.session.transition(SessionState.FAILED)
            committed = set(adapter.committed_file_ids if adapter is not None else ())
            if committed:
                files_written = len(committed)
                accepted = sum(
                    len(item.plan.changes) for item in staged if item.file_id in committed
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
                        files_scanned=len(planned),
                        changes=accepted,
                        files_changed=files_written,
                        files_without_changes=files_without_changes,
                        skipped_changes=max(0, planned_change_count - accepted),
                        committed_file_ids=sorted(committed),
                    )
                )
                _show_result_safely(
                    show_result,
                    translator=translator,
                    status="partial_failure",
                    files_scanned=len(planned),
                    files_changed=files_written,
                    accepted_changes=accepted,
                    skipped_changes=max(0, planned_change_count - accepted),
                    files_not_written=max(0, len(planned) - files_written),
                    files_without_changes=files_without_changes,
                    failed_file=getattr(exc, "failed_file_id", None),
                )
                raise
            self.logger.exception("controller_failed")
            self.logger.summary(
                self._summary(status="failed", files_scanned=0, changes=0, files_changed=0)
            )
            href_by_id = {item.source.file_id: item.source.href for item in planned}
            affected_files = tuple(
                (href_by_id.get(str(href), str(href)), tuple(codes))
                for href, codes in getattr(exc, "affected_files", ())
            )
            error_values = {
                "translator": translator,
                "kind": _error_kind(exc),
                "detail": type(exc).__name__,
                "files_written": files_written,
                "log_path": str(self.logger.log_path),
                "affected_files": affected_files,
            }
            if isinstance(exc, RuntimeSelectionError):
                error_values["summary"] = _runtime_selection_summary(exc, translator)
            _show_error_safely(
                self.logger,
                **error_values,
            )
            if isinstance(exc, RuntimeSelectionError):
                return 2
            raise
        finally:
            if backend is not None:
                backend.close()

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
        except Exception as error:  # noqa: BLE001 - bookkeeping must not undo a commit
            try:
                self.logger.exception(f"post_commit_{label}_failed", error)
            except Exception:
                print(
                    f"OpenCCForSigil: {label} failed after commit: {error}",
                    file=sys.stderr,
                )
            return default

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
        failed_file: Optional[str] = None,
        committed_file_ids: Optional[list[str]] = None,
    ) -> Dict[str, object]:
        summary: Dict[str, object] = {
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
