"""Persistent profiles/rules and immutable run settings shared by the UI."""

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from app.profiles import Profile, ProfileStore
from core.models import RuleSnapshot
from rules.store import RuleSet, RuleStore
from opencc_backend.configs import comparison_configs
from ui.qt import exec_dialog


ALIASES = {"include_nav": "convert_nav", "include_ncx": "convert_ncx",
           "include_metadata": "convert_metadata"}


def profile_options(profile):
    values = profile.to_dict()
    values.update({key: values[value] for key, value in ALIASES.items()})
    if values.get("language_region") == "auto":
        values["language_region"] = ""
    return values


class RunSettings:
    def __init__(self, storage, adapter, preferences, *, language, session_id):
        self.storage, self.adapter = storage, adapter
        self.language = language
        self.session_id = session_id
        self.profile = None
        self.backend = None
        self.profiles = ProfileStore(storage.paths.profiles)
        self.rules = RuleStore(storage.paths.rules)
        self._pending_missing_rulesets: tuple[str, ...] = ()
        self._reported_missing_rulesets: set[str] = set()
        self.recovery_notice: tuple[str, str] | None = None
        self.clear_profile_preference = False
        identifier = preferences.get("profile_id")
        if identifier:
            try:
                self.active = self.profiles.load(identifier)
            except (OSError, ValueError):
                backup_name = ""
                try:
                    path = self.profiles._path(str(identifier))
                    if path.is_file():
                        backup_name = self.storage.quarantine(path).name
                except Exception:
                    pass
                self.active = self._conservative_profile(preferences)
                self.recovery_notice = (
                    "profile_recovered", backup_name or str(identifier))
                self.clear_profile_preference = True
        else:
            self.active = self._conservative_profile(preferences)
        self.active = replace(
            self.active,
            ruleset_ids=self._validate_active_rulesets(self.active.ruleset_ids),
        )
        self._book_fingerprint = None

    def bind_run(self, profile, backend):
        """Bind the selected run profile and backend before preview actions."""

        if profile is None or backend is None:
            raise ValueError("run profile and backend must be bound")
        self.profile = profile
        self.backend = backend

    def _conservative_profile(self, preferences):
        options = preferences.get("run_options")
        saved_ids = options.get("ruleset_ids", ()) if isinstance(options, dict) else ()
        return Profile(
            id="conservative", name="Conservative",
            ruleset_ids=self._existing_ruleset_ids(saved_ids),
        )

    @property
    def active_profile_is_saved(self):
        return (self.profiles.directory / f"{self.active.id}.json").is_file()

    @property
    def book_fingerprint(self):
        if self._book_fingerprint is None:
            self._book_fingerprint = self.adapter.book_fingerprint()
        return self._book_fingerprint

    def current_profile(self, config, options):
        payload = self.active.to_dict()
        payload.update({ALIASES.get(key, key): value for key, value in options.items()
                        if key not in {"id", "name", "schema_version", "profile_id"}})
        payload["conversion"] = config
        payload["segmentation"] = "jieba" if config.endswith("_jieba") else "mmseg"
        payload["attributes"] = tuple(name for name, enabled in (
            ("alt", payload.get("convert_alt", True)),
            ("title", payload.get("convert_title", True)),
            ("aria-label", payload.get("convert_aria_label", False)),
        ) if enabled)
        payload["ruleset_ids"] = self._existing_ruleset_ids(payload.get("ruleset_ids", ()))
        profile = Profile.from_dict(payload)
        if profile.force_pivot and (not profile.pivot_chain or profile.pivot_chain[-1] != config):
            raise ValueError("force-pivot must end in the selected configuration")
        return profile

    def _existing_ruleset_ids(self, identifiers):
        if isinstance(identifiers, str):
            identifiers = (identifiers,)
        elif not isinstance(identifiers, (tuple, list, set, frozenset)):
            identifiers = ()
        values = tuple(dict.fromkeys(str(item) for item in identifiers if item))
        available = {path.stem for path in self.rules.directory.glob("*.json")}
        kept = tuple(item for item in values if item == "default" or item in available)
        missing = tuple(item for item in values if item != "default" and item not in available)
        self._pending_missing_rulesets = tuple(dict.fromkeys(
            (*self._pending_missing_rulesets, *missing)))
        return kept

    def _validate_active_rulesets(self, identifiers):
        valid = []
        for identifier in identifiers:
            path = self.rules.directory / f"{identifier}.json"
            if identifier == "default" and not path.exists():
                valid.append(identifier)
                continue
            try:
                self.rules.load(identifier)
            except (OSError, ValueError):
                if path.is_file():
                    try:
                        self.storage.quarantine(path)
                    except Exception:
                        pass
                self._pending_missing_rulesets = tuple(dict.fromkeys(
                    (*self._pending_missing_rulesets, identifier)))
                continue
            valid.append(identifier)
        return tuple(valid)

    def take_missing_rulesets_notice(self):
        pending = tuple(item for item in self._pending_missing_rulesets
                        if item not in self._reported_missing_rulesets)
        self._reported_missing_rulesets.update(pending)
        self._pending_missing_rulesets = ()
        return pending

    def pick_profile(self, config, options, translator):
        from ui.profile_window import show_profile_window

        draft = self.current_profile(config, options)
        existing, errors = self.profiles.load_all()
        values = (draft,) + tuple(item for item in existing if item.id != draft.id)
        rulesets, _rule_errors = self.rules.list()

        def profile_deleted(identifier):
            preferences = self.storage.load_preferences()
            if preferences.get("profile_id") == identifier:
                preferences.pop("profile_id", None)
                self.storage.save_preferences(preferences)

        available_configs, jieba_pending = self._available_config_options()

        selected = show_profile_window(
            values, translator=translator, store=self.profiles,
            selected_id=draft.id,
            available_configs=available_configs,
            jieba_pending=jieba_pending,
            available_rulesets=("default", *(ruleset.id for ruleset in rulesets)),
            current_profile=draft,
            active_profile=self.active,
            on_delete=profile_deleted,
            storage_errors=tuple(name for name, _error in errors),
        )
        if selected is not None:
            self.active = selected
        return selected

    def save_profile(self, config, options, translator, qt, parent):
        name, accepted = qt.QInputDialog.getText(parent, translator.text("settings.save_profile"),
                                               translator.text("settings.name"))
        if not accepted or not name.strip():
            return
        profile = replace(self.current_profile(config, options), id=str(uuid4()), name=name.strip())
        self.profiles.save(profile)
        self.active = profile

    def edit_rules(self, config, translator, qt, parent):
        from ui.rules_window import show_rules_window

        rulesets, errors = self.rules.list()
        previous = {item.id: item for item in rulesets}
        values = {item.id: item for item in rulesets}
        values.setdefault("default", RuleSet("default"))
        identifiers = tuple(dict.fromkeys((*self.active.ruleset_ids, *values)))
        initial_id = next((item for item in self.active.ruleset_ids if item in values),
                          identifiers[0] if identifiers else "default")
        for identifier in identifiers:
            values.setdefault(identifier, RuleSet(identifier))
        available_configs, jieba_pending = self._available_config_options()
        result = show_rules_window(
            values[initial_id].rules, translator=translator, official_convert=self.backend,
            config=config, profile_id=self.active.id, book_fingerprint=self.book_fingerprint,
            available_configs=available_configs,
            jieba_pending=jieba_pending,
            comparison_configs=comparison_configs(config),
            storage_errors=tuple(name for name, _error in errors),
            rulesets=tuple(values.values()), ruleset_id=initial_id,
        )
        if result is not None:
            if isinstance(result, tuple):
                # Keep compatibility with callers/tests that still provide the
                # previous rules-only result shape.
                selected_id = initial_id
                result_sets = (RuleSet(selected_id, result, values[selected_id].name),)
                renamed = ()
            else:
                selected_id = result.selected_id
                result_sets = result.rulesets
                renamed = result.renamed
            for item in result_sets:
                old = previous.get(item.id)
                if old != item and (item.id != "default" or item.rules):
                    self.rules.save(item)
            if renamed:
                self._replace_ruleset_references(renamed)
                for old_id, _new_id in renamed:
                    old_path = self.rules.directory / f"{old_id}.json"
                    old_path.unlink(missing_ok=True)
            self.rules._validate_id(selected_id)
            updated_rule_ids = tuple(dict.fromkeys(
                [dict(renamed).get(item, item) for item in self.active.ruleset_ids]
                + [selected_id]
            ))
            updated = replace(self.active, ruleset_ids=updated_rule_ids)
            if (self.active_profile_is_saved
                    and selected_id not in self.active.ruleset_ids):
                response = qt.QMessageBox.question(
                    parent, translator.text("settings.rules"),
                    translator.text("settings.add_ruleset_to_profile",
                                    ruleset=selected_id,
                                    profile=self.active.name or self.active.id),
                    qt.QMessageBox.Yes | qt.QMessageBox.No,
                    qt.QMessageBox.No,
                )
                if response == qt.QMessageBox.Yes:
                    self.profiles.save(updated)
                else:
                    qt.QMessageBox.information(
                        parent, translator.text("settings.rules"),
                        translator.text("settings.ruleset_session_only", ruleset=selected_id),
                    )
            self.active = updated

    def _available_config_options(self):
        if self.backend is None:
            return (), False
        nonblocking = getattr(self.backend, "available_configs_nonblocking", None)
        available = nonblocking() if callable(nonblocking) else self.backend.available_configs()
        return tuple(available), bool(getattr(self.backend, "jieba_probe_pending", False))

    def _replace_ruleset_references(self, renames):
        replacements = dict(renames)
        profiles, _errors = self.profiles.load_all()
        for profile in profiles:
            changed = tuple(dict.fromkeys(replacements.get(item, item)
                                          for item in profile.ruleset_ids))
            if changed != profile.ruleset_ids:
                self.profiles.save(replace(profile, ruleset_ids=changed))
        self.active = replace(
            self.active,
            ruleset_ids=tuple(dict.fromkeys(
                replacements.get(item, item) for item in self.active.ruleset_ids)),
        )

    def freeze_rules(self, profile):
        identifiers = self._existing_ruleset_ids(profile.ruleset_ids)
        rules = []
        for identifier in identifiers:
            # The built-in empty set does not need an on-disk file.
            if identifier == "default" and not (self.rules.directory / "default.json").exists():
                continue
            try:
                rules.extend(self.rules.load(identifier).rules)
            except (OSError, ValueError):
                path = self.rules.directory / f"{identifier}.json"
                if path.is_file():
                    try:
                        self.storage.quarantine(path)
                    except Exception:
                        pass
                self._pending_missing_rulesets = tuple(dict.fromkeys(
                    (*self._pending_missing_rulesets, identifier)))
        from rules.models import RuleSnapshot as Snapshot
        from rules.conflicts import validate_no_blocking_conflicts
        validate_no_blocking_conflicts(rules)
        frozen = Snapshot.freeze(rules)
        return RuleSnapshot(rules_hash=frozen.sha256, rules=frozen.rules)

    def revision(self):
        digest = sha256()
        for directory in (self.profiles.directory, self.rules.directory):
            for path in sorted(directory.glob("*.json")):
                digest.update(str(path.relative_to(self.storage.paths.root)).encode())
                digest.update(path.read_bytes())
        return digest.hexdigest()

    def snapshot_guard(self):
        expected = self.revision()

        def validate():
            if self.revision() != expected:
                raise ValueError("profiles or rules changed after preview; rescan required")
        return validate

    def checkpoint_notice_enabled(self):
        value = self.adapter.checkpoint_notice_preference()
        if value is not None:
            return bool(value)
        return self.storage.load_preferences().get("checkpoint_notice", True)

    def hide_checkpoint_notice(self):
        if not self.adapter.save_checkpoint_notice_preference(False):
            preferences = self.storage.load_preferences()
            self.storage.save_preferences({**preferences, "checkpoint_notice": False})

    def open_tool(self, name, translator, qt, parent):
        if name == "self_test":
            from app.self_test import run_self_test
            report = run_self_test(data_dir=self.storage.paths.root)
            self.show_self_test(report, translator, qt, parent)
        elif name == "history":
            from ui.history_window import show_history
            dialog = show_history(
                self.storage.paths.history, logs_root=self.storage.paths.logs,
                parent=parent, language=translator.language, translator=translator,
                on_inspect=lambda record: self.inspect_report(record, translator, qt, parent),
                on_export=lambda record, full, diff: self.export_report(
                    record, full, diff, translator, qt, parent))
            if dialog is not None:
                exec_dialog(dialog)

    @staticmethod
    def show_self_test(report, translator, qt, parent):
        payload = json.dumps(report.as_dict(), ensure_ascii=False, indent=2)
        dialog = qt.QDialog(parent)
        dialog.setWindowTitle(translator.text("settings.self_test"))
        dialog.resize(620, 480)
        layout = qt.QVBoxLayout(dialog)
        table = qt.QTableWidget(len(report.checks), 2, dialog)
        table.setHorizontalHeaderLabels((
            translator.text("settings.self_test_check"),
            translator.text("settings.self_test_result"),
        ))
        view = qt.QAbstractItemView
        no_edit = getattr(view, "NoEditTriggers", None)
        if no_edit is None:
            no_edit = getattr(getattr(view, "EditTrigger", None), "NoEditTriggers", 0)
        table.setEditTriggers(no_edit)
        selection = getattr(view, "SelectionBehavior", view)
        table.setSelectionBehavior(getattr(selection, "SelectRows", 1))
        for row, (name, passed) in enumerate(sorted(report.checks.items())):
            table.setItem(row, 0, qt.QTableWidgetItem(name))
            result = translator.text(
                "settings.self_test_passed" if passed else "settings.self_test_failed")
            table.setItem(row, 1, qt.QTableWidgetItem(result))
        layout.addWidget(table)
        details = qt.QPlainTextEdit(dialog)
        details.setReadOnly(True)
        details.setPlainText(payload)
        details.setVisible(False)
        details_button = qt.QPushButton(translator.text("settings.self_test_details"), dialog)
        details_button.clicked.connect(lambda: details.setVisible(not details.isVisible()))
        layout.addWidget(details_button)
        layout.addWidget(details)
        buttons = qt.QHBoxLayout()
        copy_button = qt.QPushButton(translator.text("settings.self_test_copy"), dialog)
        close_button = qt.QPushButton(translator.text("common.close"), dialog)
        copy_button.clicked.connect(lambda: qt.QApplication.clipboard().setText(payload))
        close_button.clicked.connect(dialog.accept)
        buttons.addWidget(copy_button)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
        exec_dialog(dialog)

    def inspect_report(self, record, translator, qt, parent):
        from logging_ext.report import render_markdown
        self.show_text(render_markdown(record["summary"], record["commit_manifest"],
                                       record["provenance"]),
                       translator.text("settings.history"), qt, parent)

    def export_report(self, record, full, diff, translator, qt, parent):
        from logging_ext.report import export_json, export_markdown
        path, _filter = qt.QFileDialog.getSaveFileName(
            parent, translator.text("settings.history"),
            str(self.storage.paths.exports / (record["session_id"] + ".md")),
            "Markdown (*.md);;JSON (*.json)")
        if not path:
            return
        exporter = export_json if path.lower().endswith(".json") else export_markdown
        try:
            exporter(Path(path), record["summary"], record["commit_manifest"], record["provenance"],
                     include_full_diff=full, full_diff=diff)
        except (OSError, ValueError) as exc:
            qt.QMessageBox.warning(parent, translator.text("settings.history"), str(exc))

    def export_preview(self, planned, previews, include_full_diff, qt, parent):
        from core.staging import apply_changes, source_sha256
        from ui.i18n import Translator
        if self.profile is None or self.backend is None:
            raise RuntimeError("run settings are not bound to an active profile and backend")
        translator = Translator(self.language)
        session_id = self.session_id
        summary = {"session_id": session_id, "status": "preview (not committed)",
                   "files_scanned": len(planned), "config": self.profile.conversion,
                   "profile_id": self.profile.id,
                   "changes": sum(len(item.plan.changes) for item in planned)}
        files, diff = [], []
        for item, preview in zip(planned, previews):
            accepted = preview.finalize(require_explicit=False)
            converted = apply_changes(item.source.source, accepted.changes)
            files.append({"id": item.source.file_id, "href": item.source.href,
                          "before_sha256": item.plan.source_sha256,
                          "after_sha256": source_sha256(converted),
                          "change_count": len(accepted.changes)})
            if include_full_diff:
                diff.extend({"file": item.source.href, "source": change.source,
                             "target": change.target, "rule_source": change.rule_source,
                             "risk": change.risk,
                             "decision": (preview.decision(change.change_id).value
                                          if preview.decision(change.change_id) else "undecided")}
                            for change in item.plan.changes)
        record = {"session_id": session_id, "summary": summary,
                  "commit_manifest": {"session_id": session_id, "files": files},
                  "provenance": self.backend.provenance().as_dict()}
        self.export_report(record, include_full_diff, diff if include_full_diff else None,
                           translator, qt, parent)

    @staticmethod
    def show_text(text, title, qt, parent):
        dialog = qt.QDialog(parent)
        dialog.setWindowTitle(title)
        dialog.resize(720, 520)
        layout = qt.QVBoxLayout(dialog)
        view = qt.QPlainTextEdit()
        view.setReadOnly(True)
        view.setPlainText(text)
        layout.addWidget(view)
        exec_dialog(dialog)


def settings_hash(profile):
    return sha256(json.dumps(profile.to_dict(), sort_keys=True,
                             ensure_ascii=False).encode()).hexdigest()


def tokenizer_policy(profile):
    from document.tokenizer import TokenizerOptions
    protected = set(profile.protected_elements) | {"script", "style"}
    for names, enabled in ((("code", "pre"), profile.convert_code_pre),
                           (("rt", "rp"), profile.convert_ruby_rt)):
        if enabled:
            protected.difference_update(names)
        else:
            protected.update(names)
    return TokenizerOptions(
        decode_numeric_cjk_refs=profile.decode_numeric_cjk_refs,
        protected_elements=tuple(sorted(protected)),
        convert_attributes=tuple(name for name, enabled in (
            ("alt", profile.convert_alt), ("title", profile.convert_title),
            ("aria-label", profile.convert_aria_label)) if enabled),
    )
