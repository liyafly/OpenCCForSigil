"""Qt profile chooser and manager."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable
from uuid import uuid4

from app.profiles import Profile, ProfileStore
from opencc_backend.configs import SUPPORTED_CONFIGS, base_config_options
from ui.i18n import CatalogView, Translator, show_error_details
from ui.qt import ensure_application, exec_dialog, load_qt






def _labels(translator: Any) -> CatalogView:
    return CatalogView(translator or Translator("en"), "profile")


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
    jieba_pending: bool = False,
) -> Profile | None:
    qt = load_qt()
    ensure_application(qt)
    manager = ProfileManagerDialog(
        qt, tuple(profiles), translator=translator, store=store, selected_id=selected_id,
        available_configs=available_configs, available_rulesets=available_rulesets,
        current_profile=current_profile, active_profile=active_profile, on_delete=on_delete,
        storage_errors=storage_errors, jieba_pending=jieba_pending,
    )
    exec_dialog(manager.dialog)
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
        jieba_pending: bool = False,
    ) -> None:
        self._qt = qt_widgets
        self._translator = translator or Translator("en")
        self._labels = _labels(self._translator)
        self._profiles = list(profiles)
        self._store = store
        self._on_delete = on_delete
        self._storage_errors = tuple(storage_errors)
        self._jieba_pending = bool(jieba_pending)
        self._current_profile = current_profile or (self._profiles[0] if self._profiles else None)
        self._active_profile = active_profile
        available = tuple(SUPPORTED_CONFIGS if available_configs is None else available_configs)
        self._available_configs = base_config_options(available)
        self._available_config_ids = set(available)
        self._available_rulesets = tuple(dict.fromkeys(
            ("default", *available_rulesets,
             *(identifier for profile in self._profiles for identifier in profile.ruleset_ids))))
        self._selected_id = selected_id
        self.selected: Profile | None = None
        self.accepted = False
        self.dialog = qt_widgets.QDialog()
        self.dialog.setWindowTitle(self._labels["title"])
        self.dialog.resize(780, 500)
        self._build()
        self._refresh()

    def _build(self) -> None:
        qt = self._qt
        root = qt.QVBoxLayout(self.dialog)
        self.jieba_notice = None
        if self._jieba_pending:
            self.jieba_notice = qt.QLabel(self._translator.text("config.jieba_checking"))
            self.jieba_notice.setWordWrap(True)
            root.addWidget(self.jieba_notice)
        if self._storage_errors:
            notice = qt.QLabel(self._labels["skipped_files"].format(
                files=", ".join(self._storage_errors)))
            notice.setWordWrap(True)
            root.addWidget(notice)
        content = qt.QHBoxLayout()
        self.profile_list = qt.QListWidget()
        content.addWidget(self.profile_list, 1)
        right = qt.QVBoxLayout()
        right.addWidget(qt.QLabel(self._labels["summary"]))
        self.summary = qt.QPlainTextEdit()
        self.summary.setReadOnly(True)
        right.addWidget(self.summary, 1)
        self.rules_group = qt.QGroupBox(self._labels["rules"])
        self.rules_layout = qt.QVBoxLayout(self.rules_group)
        self.rules_checks = {}
        for identifier in self._available_rulesets:
            check = qt.QCheckBox(identifier, self.rules_group)
            self.rules_layout.addWidget(check)
            self.rules_checks[identifier] = check
        right.addWidget(self.rules_group)
        content.addLayout(right, 2)
        root.addLayout(content, 1)

        actions = qt.QHBoxLayout()
        self.use_button = qt.QPushButton(self._labels["use"])
        self.rename_button = qt.QPushButton(self._labels["rename"])
        self.copy_button = qt.QPushButton(self._labels["copy"])
        self.delete_button = qt.QPushButton(self._labels["delete"])
        self.from_current_button = qt.QPushButton(self._labels["from_current"])
        self.close_button = qt.QPushButton(self._labels["close"])
        for button in (self.use_button, self.rename_button, self.copy_button,
                       self.delete_button, self.from_current_button, self.close_button):
            actions.addWidget(button)
        root.addLayout(actions)
        self.profile_list.currentRowChanged.connect(self._refresh_summary)
        self.use_button.clicked.connect(self._use)
        self.rename_button.clicked.connect(self._rename)
        self.copy_button.clicked.connect(self._copy)
        self.delete_button.clicked.connect(self._delete)
        self.from_current_button.clicked.connect(self._from_current)
        self.close_button.clicked.connect(self.dialog.reject)

    def _refresh(self) -> None:
        self.profile_list.clear()
        selected_row = -1
        role = getattr(self._qt.Qt, "UserRole", 32)
        for row, profile in enumerate(self._profiles):
            item = self._qt.QListWidgetItem(profile.name or profile.id)
            item.setData(role, profile.id)
            self.profile_list.addItem(item)
            if profile.id == self._selected_id:
                selected_row = row
        if self._profiles:
            self.profile_list.setCurrentRow(selected_row if selected_row >= 0 else 0)
        self._refresh_summary()

    def _current(self) -> Profile | None:
        row = self.profile_list.currentRow()
        return self._profiles[row] if 0 <= row < len(self._profiles) else None

    def _refresh_summary(self, *_args) -> None:
        profile = self._current()
        if profile is None:
            self.summary.clear()
            self.use_button.setEnabled(False)
            self.rename_button.setEnabled(False)
            self.copy_button.setEnabled(False)
            self.delete_button.setEnabled(False)
            return
        conversion = profile.conversion
        unavailable = conversion.endswith("_jieba") and conversion not in self._available_config_ids
        status_label = (
            self._translator.text("config.jieba_checking")
            if unavailable and self._jieba_pending
            else self._labels["unavailable"] if unavailable else ""
        )
        status = f" ({status_label})" if status_label else ""
        options = ", ".join(
            f"{key}: {'on' if getattr(profile, field) else 'off'}"
            for key, field in (("NAV", "convert_nav"), ("NCX", "convert_ncx"),
                               ("metadata", "convert_metadata"),
                               ("alt", "convert_alt"), ("title", "convert_title")))
        values = (
            f"{self._labels['conversion']}: {conversion}{status}",
            f"{self._labels['options']}: {options}",
            f"{self._labels['rules']}: {', '.join(profile.ruleset_ids) or '—'}",
        )
        self.summary.setPlainText("\n".join(values))
        for identifier, check in self.rules_checks.items():
            check.setChecked(identifier in profile.ruleset_ids)
        self.use_button.setEnabled(True)
        exists = self._profile_is_saved(profile)
        self.rename_button.setEnabled(exists and self._can_delete(profile))
        self.copy_button.setEnabled(True)
        self.delete_button.setEnabled(exists and self._can_delete(profile))

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
            self.dialog, self._labels["title"], prompt, text=value)
        if not accepted:
            return None
        name = str(name).strip()
        if not name:
            self._warn(self._labels["invalid_name"])
            return None
        if any(item.name.casefold() == name.casefold()
               and item.id != exclude_id for item in self._profiles):
            self._warn(self._labels["duplicate_name"])
            return None
        return name

    def _rename(self) -> None:
        profile = self._current()
        if profile is None or not self._profile_is_saved(profile):
            return
        name = self._ask_name(self._labels["ask_name"], profile.name, exclude_id=profile.id)
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
        name = self._ask_name(self._labels["ask_name"], profile.name + self._labels["copied"])
        if name is None:
            return
        copied = replace(profile, id=str(uuid4()), name=name)
        if not self._save_profile(copied):
            return
        self._profiles.append(copied)
        self._selected_id = copied.id
        self._refresh()

    def _from_current(self) -> None:
        if self._current_profile is None or self._store is None:
            return
        name = self._ask_name(self._labels["ask_name"], self._current_profile.name)
        if name is None:
            return
        created = replace(self._current_profile, id=str(uuid4()), name=name)
        if not self._save_profile(created):
            return
        self._profiles.append(created)
        self._selected_id = created.id
        self._refresh()

    def _delete(self) -> None:
        profile = self._current()
        if profile is None or self._store is None or not self._profile_is_saved(profile):
            return
        if not self._can_delete(profile):
            self._warn(self._labels["delete_modified"])
            return
        answer = self._qt.QMessageBox.question(
            self.dialog, self._labels["title"],
            self._labels["confirm_delete"].format(name=profile.name),
        )
        yes = getattr(self._qt.QMessageBox, "Yes", getattr(
            getattr(self._qt.QMessageBox, "StandardButton", object), "Yes", None))
        if answer != yes:
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
        self._refresh()

    def _replace_profile(self, old: Profile, new: Profile) -> None:
        index = self._profiles.index(old)
        self._profiles[index] = new
        self._selected_id = new.id
        self._refresh()

    def _warn(self, message: str) -> None:
        self._qt.QMessageBox.warning(self.dialog, self._labels["title"], message)

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
    payload.pop("id", None)
    payload.pop("name", None)
    return tuple(sorted((key, tuple(value) if isinstance(value, list) else value)
                        for key, value in payload.items()))


__all__ = ["ProfileManagerDialog", "show_profile_window"]
