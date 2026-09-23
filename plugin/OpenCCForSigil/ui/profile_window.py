"""Qt profile chooser and manager."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable
from uuid import uuid4

from app.profiles import Profile, ProfileStore
from opencc_backend.configs import SUPPORTED_CONFIGS, V1_CONFIGS


_LABELS = {
    "en": {
        "title": "Profiles", "use": "Use", "rename": "Rename", "copy": "Copy",
        "delete": "Delete", "from_current": "From current settings", "close": "Close",
        "summary": "Profile summary", "conversion": "Direction", "rules": "Rule sets",
        "options": "Options", "jieba": "Advanced Jieba", "unavailable": "unavailable on this host",
        "ask_name": "Profile name", "duplicate_name": "A profile with this name already exists.",
        "invalid_name": "Profile name cannot be empty.", "confirm_delete": "Delete profile {name}?",
        "delete_modified": "Save the current settings as a new profile before deleting this modified profile.",
        "copied": " copy", "skipped_files": "Corrupt profiles skipped: {files}",
        "not_selected": "Select a profile first.",
    },
    "zh-Hans": {
        "title": "配置方案", "use": "使用", "rename": "重命名", "copy": "复制",
        "delete": "删除", "from_current": "从当前设置新建", "close": "关闭",
        "summary": "方案摘要", "conversion": "转换方向", "rules": "规则集",
        "options": "主要选项", "jieba": "高级 Jieba", "unavailable": "本机不可用",
        "ask_name": "方案名称", "duplicate_name": "已有同名方案。",
        "invalid_name": "方案名称不能为空。", "confirm_delete": "删除方案“{name}”？",
        "delete_modified": "当前设置已有修改，请先从当前设置新建方案，再删除此方案。",
        "copied": " 副本", "skipped_files": "已跳过损坏的方案文件：{files}",
        "not_selected": "请先选择方案。",
    },
    "zh-Hant": {
        "title": "設定檔", "use": "使用", "rename": "重新命名", "copy": "複製",
        "delete": "刪除", "from_current": "從目前設定新建", "close": "關閉",
        "summary": "設定檔摘要", "conversion": "轉換方向", "rules": "規則集",
        "options": "主要選項", "jieba": "進階 Jieba", "unavailable": "此主機不可用",
        "ask_name": "設定檔名稱", "duplicate_name": "已有同名設定檔。",
        "invalid_name": "設定檔名稱不可空白。", "confirm_delete": "刪除設定檔「{name}」？",
        "delete_modified": "目前設定已有修改，請先從目前設定新建設定檔，再刪除此設定檔。",
        "copied": " 副本", "skipped_files": "已略過損毀的設定檔：{files}",
        "not_selected": "請先選取設定檔。",
    },
}


def _labels(translator: Any) -> dict[str, str]:
    return _LABELS.get(getattr(translator, "language", "en"), _LABELS["en"])


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
) -> Profile | None:
    qt = _load_qt_widgets()
    _ensure_application(qt)
    manager = ProfileManagerDialog(
        qt, tuple(profiles), translator=translator, store=store, selected_id=selected_id,
        available_configs=available_configs, available_rulesets=available_rulesets,
        current_profile=current_profile, active_profile=active_profile, on_delete=on_delete,
        storage_errors=storage_errors,
    )
    exec_method = getattr(manager.dialog, "exec", None) or manager.dialog.exec_
    exec_method()
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
    ) -> None:
        self._qt = qt_widgets
        self._labels = _labels(translator)
        self._profiles = list(profiles)
        self._store = store
        self._on_delete = on_delete
        self._storage_errors = tuple(storage_errors)
        self._current_profile = current_profile or (self._profiles[0] if self._profiles else None)
        self._active_profile = active_profile
        available = tuple(SUPPORTED_CONFIGS if available_configs is None else available_configs)
        self._available_configs = _base_config_options(available)
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
        status = (f" ({self._labels['unavailable']})"
                  if conversion.endswith("_jieba") and conversion not in self._available_config_ids
                  else "")
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
        self._store.save(updated)
        self._replace_profile(profile, updated)

    def _copy(self) -> None:
        profile = self._current()
        if profile is None or self._store is None:
            return
        name = self._ask_name(self._labels["ask_name"], profile.name + self._labels["copied"])
        if name is None:
            return
        copied = replace(profile, id=str(uuid4()), name=name)
        self._store.save(copied)
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
        self._store.save(created)
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
        path = self._store._path(profile.id)
        path.unlink(missing_ok=True)
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


def _profile_signature(profile: Profile) -> tuple:
    payload = profile.to_dict()
    payload.pop("id", None)
    payload.pop("name", None)
    return tuple(sorted((key, tuple(value) if isinstance(value, list) else value)
                        for key, value in payload.items()))


def _load_qt_widgets() -> Any:
    try:
        from PySide6 import QtCore, QtWidgets

        QtWidgets.Qt = QtCore.Qt
        return QtWidgets
    except ImportError:
        try:
            from PyQt5 import QtCore, QtWidgets

            QtWidgets.Qt = QtCore.Qt
            return QtWidgets
        except ImportError as exc:
            raise RuntimeError("Sigil Qt runtime is unavailable") from exc


_application: Any = None


def _base_config_options(available_configs: Iterable[str] | None) -> tuple[str, ...]:
    values = tuple(V1_CONFIGS if available_configs is None else available_configs)
    seen = set(values)
    from opencc_backend.configs import BASE_CONFIG_BY_JIEBA
    seen.update(BASE_CONFIG_BY_JIEBA[value] for value in values if value in BASE_CONFIG_BY_JIEBA)
    return tuple(config for config in V1_CONFIGS if config in seen)


def _ensure_application(qt: Any) -> Any:
    global _application
    app = qt.QApplication.instance()
    if app is None:
        import sys

        app = qt.QApplication(sys.argv)
    _application = app
    return app


__all__ = ["ProfileManagerDialog", "STANDARD_CONFIGS", "show_profile_window"]
STANDARD_CONFIGS = V1_CONFIGS
