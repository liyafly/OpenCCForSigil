"""Qt profile chooser and manager."""

from __future__ import annotations

from dataclasses import fields, replace
from typing import Any, Iterable
from uuid import uuid4

from app.profiles import Profile, ProfileStore
from app.settings import _duplicate_profile_name
from opencc_backend.configs import SUPPORTED_CONFIGS, base_config_options
from ui.i18n import (
    CatalogView,
    Translator,
    configuration_label,
    profile_display_name,
    plugin_window_title,
    show_error_details,
)
from ui.qt import ask_confirmation, ensure_application, exec_dialog, load_qt
from ui.window_state import restore_window_size, save_window_size
from ui.profile_compare import compare_profile_settings






def _labels(translator: Any) -> CatalogView:
    return CatalogView(translator or Translator("en"), "profile")


_PROFILE_SUMMARY_KEYS = {
    "conversion": "profile.conversion",
    "segmentation": "profile.segmentation",
    "convert_nav": "options.include_nav",
    "convert_ncx": "options.include_ncx",
    "convert_metadata": "options.include_metadata",
    "convert_alt": "options.convert_alt",
    "convert_title": "options.convert_title",
    "convert_aria_label": "options.convert_aria_label",
    "convert_ruby_rt": "options.convert_ruby_rt",
    "convert_code_pre": "options.convert_code_pre",
    "decode_numeric_cjk_refs": "options.decode_numeric_cjk_refs",
    "quotation_mode": "options.quotation_mode",
    "punctuation_mode": "options.punctuation_mode",
    "language_metadata": "options.language_metadata",
    "language_preset": "options.language_preset",
    "language_region": "options.language_region",
    "ruleset_ids": "profile.rules",
    "builtin_rules_enabled": "options.builtin_rules_enabled",
    "attributes": "profile.attributes",
    "protected_elements": "profile.protected_elements",
    "mathml": "profile.mathml",
    "force_pivot": "options.force_pivot",
    "pivot_chain": "options.pivot_chain",
}

_PROFILE_SUMMARY_NON_OPTIONS = {"schema_version", "id", "name", "extras"}
_PROFILE_SUMMARY_OMITTED_FIELDS = {
    "scope", "preview_required", "tofu_policy", "regex_rules",
    "convert_svg_text", "review_annotations", "checkpoint_notice",
    "numeric_cjk_char_refs",
}
_PROFILE_COMPARISON_PRIORITY = (
    "conversion", "segmentation", "ruleset_ids", "force_pivot",
    "pivot_chain", "mathml", "decode_numeric_cjk_refs", "builtin_rules_enabled",
)


def _profile_summary_value(profile: Profile, name: str, translator: Translator) -> str:
    value = getattr(profile, name)
    if name == "mathml":
        return translator.text(
            "profile.mathml_scope_enabled" if value else "profile.disabled")
    if isinstance(value, bool):
        return translator.text("profile.enabled" if value else "profile.disabled")
    if name == "conversion":
        return configuration_label(translator, value)
    if name == "segmentation":
        key = "profile.segmentation.jieba" if value == "jieba" else "profile.segmentation.mmseg"
        return translator.text(key)
    if name in {"quotation_mode", "punctuation_mode", "language_metadata", "language_preset"}:
        return translator.text(f"options.{value}")
    if name == "language_region":
        regions = {"": "no_region"}
        key = f"options.{regions.get(value, value)}"
        return translator.text(key)
    if name == "pivot_chain":
        return ", ".join(configuration_label(translator, item) for item in value) or translator.text(
            "profile.no_value"
        )
    if name == "attributes":
        labels = {
            "alt": "options.convert_alt",
            "title": "options.convert_title",
            "aria-label": "options.convert_aria_label",
        }
        return ", ".join(translator.text(labels.get(item, item)) for item in value) or translator.text(
            "profile.no_value"
        )
    if name == "protected_elements":
        labels = []
        for item in value:
            key = f"profile.element.{item}"
            label = translator.text(key)
            labels.append(item if label == key else label)
        return ", ".join(labels) or translator.text("profile.no_value")
    if name == "ruleset_ids":
        return ", ".join(value) or translator.text("profile.no_value")
    if name == "numeric_cjk_char_refs":
        key = f"options.{value}"
        label = translator.text(key)
        return str(value) if label == key else label
    return str(value)


def show_profile_window(
    profiles: Iterable[Profile],
    *,
    translator: Any = None,
    store: ProfileStore | None = None,
    selected_id: str | None = None,
    available_configs: Iterable[str] | None = None,
    available_rulesets: Iterable[str] = (),
    current_profile: Profile | None = None,
    active_profile: Profile | None = None,
    on_delete=None,
    storage_errors: Iterable[str] = (),
    ui_preferences=None,
    save_ui_preferences=None,
) -> Profile | None:
    qt = load_qt()
    active_translator = translator or Translator("en")
    ensure_application(qt, language=active_translator.language)
    manager = ProfileManagerDialog(
        qt, tuple(profiles), translator=active_translator, store=store, selected_id=selected_id,
        available_configs=available_configs, available_rulesets=available_rulesets,
        current_profile=current_profile, active_profile=active_profile, on_delete=on_delete,
        storage_errors=storage_errors,
        ui_preferences=ui_preferences,
    )
    exec_dialog(manager.dialog)
    save_window_size(manager.dialog, "profile_dialog_size", save_ui_preferences)
    return manager.selected if manager.accepted else None


class ProfileManagerDialog:
    def __init__(
        self,
        qt_widgets: Any,
        profiles: tuple[Profile, ...],
        *,
        translator: Any = None,
        store: ProfileStore | None = None,
        selected_id: str | None = None,
        available_configs: Iterable[str] | None = None,
        available_rulesets: Iterable[str] = (),
        current_profile: Profile | None = None,
        active_profile: Profile | None = None,
        on_delete=None,
        storage_errors: Iterable[str] = (),
        ui_preferences=None,
    ) -> None:
        self._qt = qt_widgets
        self._translator = translator or Translator("en")
        self._labels = _labels(self._translator)
        self._profiles = list(profiles)
        self._store = store
        self._on_delete = on_delete
        self._storage_errors = tuple(storage_errors)
        self._ui_preferences = dict(ui_preferences or {})
        self._current_profile = current_profile or (self._profiles[0] if self._profiles else None)
        self._active_profile = active_profile
        available = tuple(SUPPORTED_CONFIGS if available_configs is None else available_configs)
        self._available_configs = base_config_options(available)
        self._available_config_ids = set(available)
        self._available_rulesets = tuple(dict.fromkeys(
            ("default", *available_rulesets,
             *(identifier for profile in self._profiles for identifier in profile.ruleset_ids))))
        self._selected_id = selected_id
        self._restore_id = selected_id
        self.selected: Profile | None = None
        self.accepted = False
        self.dialog = qt_widgets.QDialog()
        self.dialog.setWindowTitle(
            plugin_window_title(self._translator, self._labels["title"]))
        restore_window_size(
            self.dialog, self._ui_preferences, "profile_dialog_size", (780, 500))
        self._build()
        self._refresh()

    def _build(self) -> None:
        qt = self._qt
        root = qt.QVBoxLayout(self.dialog)
        if self._storage_errors:
            notice = qt.QLabel(self._labels["skipped_files"].format(
                files=", ".join(self._storage_errors)))
            notice.setWordWrap(True)
            root.addWidget(notice)
        content = qt.QHBoxLayout()
        self.search_edit = qt.QLineEdit()
        self.search_edit.setPlaceholderText(self._labels["search_placeholder"])
        root.addWidget(self.search_edit)
        self.count_label = qt.QLabel()
        root.addWidget(self.count_label)
        self.empty_label = qt.QLabel()
        self.empty_label.setWordWrap(True)
        self.empty_label.setVisible(False)
        root.addWidget(self.empty_label)
        self.profile_list = qt.QListWidget()
        content.addWidget(self.profile_list, 1)
        right = qt.QVBoxLayout()
        right.addWidget(qt.QLabel(self._labels["summary"]))
        self.detail_tabs = qt.QTabWidget()
        self.main_summary = qt.QPlainTextEdit()
        self.comparison_summary = qt.QPlainTextEdit()
        self.summary = qt.QPlainTextEdit()
        for view in (self.main_summary, self.comparison_summary, self.summary):
            view.setReadOnly(True)
        self.detail_tabs.addTab(self.main_summary, self._labels["main_settings"])
        self.detail_tabs.addTab(self.comparison_summary, self._labels["compare_settings"])
        self.detail_tabs.addTab(self.summary, self._labels["all_settings"])
        right.addWidget(self.detail_tabs, 1)
        self.rules_group = qt.QGroupBox(self._labels["rules"])
        self.rules_layout = qt.QVBoxLayout(self.rules_group)
        self.ruleset_note = qt.QLabel(self._translator.text("profile.rulesets_session_only"))
        self.ruleset_note.setWordWrap(True)
        self.rules_layout.addWidget(self.ruleset_note)
        self.rules_scroll = qt.QScrollArea()
        self.rules_scroll.setWidgetResizable(True)
        rules_content = qt.QWidget()
        rules_content_layout = qt.QVBoxLayout(rules_content)
        self.rules_checks = {}
        for identifier in self._available_rulesets:
            check = qt.QCheckBox(identifier, rules_content)
            check.setToolTip(identifier)
            check.stateChanged.connect(self._refresh_summary)
            rules_content_layout.addWidget(check)
            self.rules_checks[identifier] = check
        rules_content_layout.addStretch(1)
        self.rules_scroll.setWidget(rules_content)
        self.rules_scroll.setMinimumHeight(100)
        self.rules_scroll.setMaximumHeight(210)
        self.rules_layout.addWidget(self.rules_scroll)
        right.addWidget(self.rules_group)
        content.addLayout(right, 2)
        root.addLayout(content, 1)

        actions = qt.QHBoxLayout()
        self.use_button = qt.QPushButton(self._labels["use"])
        self.rename_button = qt.QPushButton(self._labels["rename"])
        self.copy_button = qt.QPushButton(self._labels["copy"])
        self.delete_button = qt.QPushButton(self._labels["delete"])
        self.close_button = qt.QPushButton(self._labels["close"])
        for button in (self.rename_button, self.copy_button, self.delete_button):
            actions.addWidget(button)
        actions.addStretch(1)
        actions.addWidget(self.close_button)
        actions.addWidget(self.use_button)
        self.actions_layout = actions
        root.addLayout(actions)
        self.search_edit.textChanged.connect(self._filter_profiles)
        self.profile_list.currentRowChanged.connect(self._selection_changed)
        self.use_button.clicked.connect(self._use)
        self.rename_button.clicked.connect(self._rename)
        self.copy_button.clicked.connect(self._copy)
        self.delete_button.clicked.connect(self._delete)
        self.close_button.clicked.connect(self.dialog.reject)

    def _refresh(self) -> None:
        preferred_id = self._selected_id or self._restore_id
        self._populate_visible_profiles(preferred_id)
        self._set_ruleset_checks(self._current())
        self._refresh_summary()

    def _populate_visible_profiles(self, preferred_id: str | None = None) -> None:
        previously_blocked = self.profile_list.blockSignals(True)
        self.profile_list.clear()
        role = getattr(self._qt.Qt, "UserRole", 32)
        query = str(self.search_edit.text()).strip().casefold()
        visible = [profile for profile in self._profiles
                   if self._matches_search(profile, query)]
        visible.sort(key=lambda profile: (
            profile_display_name(profile, self._translator).casefold(), profile.id))
        for profile in visible:
            display_name = profile_display_name(profile, self._translator)
            item = self._qt.QListWidgetItem(display_name)
            item.setToolTip(display_name)
            item.setData(role, profile.id)
            self.profile_list.addItem(item)
        visible_ids = {profile.id for profile in visible}
        if preferred_id not in visible_ids:
            preferred_id = None
        if preferred_id is None and not query and visible:
            preferred_id = visible[0].id
        selected_row = next((row for row, profile in enumerate(visible)
                             if profile.id == preferred_id), -1)
        self.profile_list.setCurrentRow(selected_row)
        self.profile_list.blockSignals(previously_blocked)
        self._selected_id = preferred_id
        self.count_label.setText(self._labels["count"].format(
            visible=len(visible), total=len(self._profiles)))
        empty = not visible
        self.empty_label.setText(
            self._labels["no_matches"] if query else self._labels["no_profiles"])
        self.empty_label.setVisible(empty)

    def _matches_search(self, profile: Profile, query: str) -> bool:
        if not query:
            return True
        searchable = " ".join((
            profile_display_name(profile, self._translator), profile.id,
            profile.conversion,
            configuration_label(self._translator, profile.conversion),
        )).strip().casefold()
        return query in searchable

    def _filter_profiles(self, *_args) -> None:
        current = self._current()
        if current is not None:
            self._restore_id = current.id
        query = str(self.search_edit.text()).strip()
        if query:
            preferred_id = (current.id if current and self._matches_search(current, query)
                            else None)
        else:
            preferred_id = self._restore_id
        self._populate_visible_profiles(preferred_id)
        self._set_ruleset_checks(self._current())
        self._refresh_summary()

    def _item_profile_id(self, item):
        if item is None:
            return None
        role = getattr(self._qt.Qt, "UserRole", 32)
        return item.data(role)

    def _current(self) -> Profile | None:
        current_item = getattr(self.profile_list, "currentItem", None)
        item = current_item() if callable(current_item) else None
        identifier = self._item_profile_id(item)
        if identifier:
            return next((profile for profile in self._profiles if profile.id == identifier), None)
        # Keep compatibility with simple fake-list tests. Real Qt always takes the
        # stable-ID branch above, so filtered row numbers never index _profiles.
        row = self.profile_list.currentRow()
        return self._profiles[row] if 0 <= row < len(self._profiles) else None

    def _selection_changed(self, *_args) -> None:
        profile = self._current()
        self._selected_id = profile.id if profile is not None else None
        if profile is not None:
            self._restore_id = profile.id
        self._set_ruleset_checks(profile)
        self._refresh_summary()

    def _set_ruleset_checks(self, profile: Profile | None) -> None:
        for identifier, check in getattr(self, "rules_checks", {}).items():
            previously_blocked = check.blockSignals(True)
            check.setChecked(profile is not None and identifier in profile.ruleset_ids)
            check.blockSignals(previously_blocked)

    def _refresh_summary(self, *_args) -> None:
        profile = self._current()
        if profile is None:
            for name in ("main_summary", "comparison_summary"):
                view = getattr(self, name, None)
                if view is not None:
                    view.clear()
            self.summary.clear()
            for button in (self.use_button, self.rename_button,
                           self.copy_button, self.delete_button):
                button.setEnabled(False)
            return

        all_options = self._profile_options_text(profile)
        main_names = ("conversion", "segmentation", "ruleset_ids",
                      "builtin_rules_enabled", "force_pivot", "pivot_chain")
        main_options = [self._profile_option_text(profile, name)
                        for name in main_names if hasattr(profile, name)]
        main_summary = getattr(self, "main_summary", None)
        if main_summary is not None:
            main_summary.setPlainText("\n".join(main_options))
        self.summary.setPlainText("\n".join(all_options))
        if profile.extras:
            extra_rows = [f"{key}: {value}" for key, value in profile.extras]
            self.summary.setPlainText("\n".join((*all_options, *extra_rows)))

        candidate = replace(profile, ruleset_ids=self._edited_rulesets(profile))
        changes = compare_profile_settings(self._current_profile or profile, candidate)
        comparison_summary = getattr(self, "comparison_summary", None)
        if comparison_summary is not None and changes:
            priority = [name for name in _PROFILE_COMPARISON_PRIORITY
                        if any(change[0] == name for change in changes)]
            ordered = priority + [name for name, _old, _new in changes
                                  if name not in priority]
            by_name = {name: (old, new) for name, old, new in changes}
            lines = [self._format_comparison(name, *by_name[name]) for name in ordered]
            comparison_summary.setPlainText("\n".join(lines))
        elif comparison_summary is not None:
            comparison_summary.setPlainText(self._labels["same_config"])
        if comparison_summary is not None:
            if self._current_profile is not None:
                comparison_summary.appendPlainText(self._labels["scope_boundary"])
            comparison_summary.appendPlainText(self._labels["rulesets_session_only"])
        self.use_button.setEnabled(True)
        exists = self._profile_is_saved(profile)
        self.rename_button.setEnabled(exists and self._can_delete(profile))
        self.copy_button.setEnabled(True)
        self.delete_button.setEnabled(exists and self._can_delete(profile))

    def _profile_options_text(self, profile: Profile) -> list[str]:
        return [self._profile_option_text(profile, profile_field.name)
                for profile_field in fields(profile)
                if profile_field.name not in {
                    *_PROFILE_SUMMARY_NON_OPTIONS,
                    *_PROFILE_SUMMARY_OMITTED_FIELDS,
                }]

    def _profile_option_text(self, profile: Profile, name: str) -> str:
        value = _profile_summary_value(profile, name, self._translator)
        if name == "conversion":
            if profile.conversion not in self._available_config_ids:
                status = self._labels["unavailable"]
            else:
                status = self._labels["available"]
            value += self._translator.text("profile.status", status=status)
        label_key = _PROFILE_SUMMARY_KEYS.get(name, f"profile.{name}")
        label = self._translator.text(label_key)
        return self._translator.text(
            "profile.summary_option", label=label,
            separator=self._translator.text("common.label_separator"), value=value)

    def _format_comparison(self, name, old, new) -> str:
        before = self._profile_value_text(name, old)
        after = self._profile_value_text(name, new)
        label_key = _PROFILE_SUMMARY_KEYS.get(name, f"profile.{name}")
        label = self._translator.text(label_key)
        return self._labels["comparison_change"].format(
            label=label, before=before, after=after)

    def _profile_value_text(self, name, value):
        if name == "conversion":
            label = configuration_label(self._translator, value).replace(" → ", " to ")
            if value not in self._available_config_ids:
                status = self._labels["unavailable"]
            else:
                status = self._labels["available"]
            return f"{label} ({status})"
        temporary = replace(Profile(id="compare", name="compare"), **{name: value})
        return _profile_summary_value(temporary, name, self._translator)

    def _profile_is_saved(self, profile: Profile) -> bool:
        return bool(self._store and (self._store.directory / f"{profile.id}.json").is_file())

    def _can_delete(self, profile: Profile) -> bool:
        if self._active_profile is None or profile.id != self._active_profile.id:
            return True
        if self._current_profile is None:
            return True
        return _profile_signature(self._current_profile) == _profile_signature(self._active_profile)

    def _edited_rulesets(self, profile: Profile) -> tuple[str, ...]:
        selected = tuple(identifier for identifier, check in self.rules_checks.items()
                         if check.isChecked())
        return tuple(identifier for identifier in self._available_rulesets if identifier in selected)

    def _use(self) -> None:
        profile = self._current()
        if profile is None:
            self._warn(self._labels["not_selected"])
            return
        self.selected = replace(profile, ruleset_ids=self._edited_rulesets(profile))
        self.accepted = True
        self.dialog.accept()

    def _ask_name(self, prompt: str, value: str = "", *, exclude_id: str | None = None) -> str | None:
        name, accepted = self._qt.QInputDialog.getText(
            self.dialog, plugin_window_title(self._translator, self._labels["title"]),
            prompt, text=value)
        if not accepted:
            return None
        name = str(name).strip()
        if not name:
            self._warn(self._labels["invalid_name"])
            return None
        existing = tuple(item for item in self._profiles if item.id != exclude_id)
        if _duplicate_profile_name(name, existing):
            self._warn(self._labels["duplicate_name"])
            return None
        return name

    def _rename(self) -> None:
        profile = self._current()
        if profile is None or not self._profile_is_saved(profile):
            return
        name = self._ask_name(
            self._labels["ask_name"], profile_display_name(profile, self._translator),
            exclude_id=profile.id,
        )
        if name is None:
            return
        updated = replace(profile, name=name)
        if not self._save_profile(updated):
            return
        self._replace_profile(profile, updated)

    def _copy(self) -> None:
        profile = self._current()
        if profile is None or self._store is None:
            return
        name = self._ask_name(
            self._labels["ask_name"],
            profile_display_name(profile, self._translator) + self._labels["copied"],
        )
        if name is None:
            return
        copied = replace(profile, id=str(uuid4()), name=name)
        if not self._save_profile(copied):
            return
        self._profiles.append(copied)
        self._selected_id = copied.id
        self._restore_id = copied.id
        self._refresh()

    def _delete(self) -> None:
        profile = self._current()
        if profile is None or self._store is None or not self._profile_is_saved(profile):
            return
        if not self._can_delete(profile):
            self._warn(self._labels["delete_modified"])
            return
        if not ask_confirmation(
                self._qt, self.dialog, self._labels["title"],
                self._labels["confirm_delete"].format(
                    name=profile_display_name(profile, self._translator)), self._translator):
            return
        try:
            path = self._store._path(profile.id)
            path.unlink(missing_ok=True)
        except OSError as exc:
            self._show_error(exc)
            return
        self._profiles.remove(profile)
        if callable(self._on_delete):
            self._on_delete(profile.id)
        self._selected_id = self._profiles[0].id if self._profiles else None
        self._restore_id = self._selected_id
        self._refresh()

    def _replace_profile(self, old: Profile, new: Profile) -> None:
        index = self._profiles.index(old)
        self._profiles[index] = new
        self._selected_id = new.id
        self._restore_id = new.id
        self._refresh()

    def _warn(self, message: str) -> None:
        self._qt.QMessageBox.warning(
            self.dialog, plugin_window_title(self._translator, self._labels["title"]), message)

    def _save_profile(self, profile: Profile) -> bool:
        try:
            self._store.save(profile)
        except (OSError, ValueError) as exc:
            self._show_error(exc)
            return False
        return True

    def _show_error(self, error: BaseException) -> None:
        show_error_details(
            self._qt, self.dialog, self._labels["title"],
            self._translator.text("profile.operation_failed"), str(error),
        )


def _profile_signature(profile: Profile) -> tuple:
    payload = profile.to_dict()
    payload.pop("diagnose_mixed", None)
    payload.pop("detailed_classification", None)
    payload.pop("id", None)
    payload.pop("name", None)
    return tuple(sorted((key, tuple(value) if isinstance(value, list) else value)
                        for key, value in payload.items()))


__all__ = ["ProfileManagerDialog", "show_profile_window"]
