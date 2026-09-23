"""Small functional profile picker/editor with three-language labels."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable

from app.profiles import Profile, ProfileStore, ProfileValidationError
from opencc_backend.configs import BASE_CONFIG_BY_JIEBA, JIEBA_CONFIG_BY_BASE, SUPPORTED_CONFIGS, V1_CONFIGS


_LABELS = {
    "en": {
        "title": "Profiles",
        "name": "Name",
        "config": "Conversion",
        "rules": "Rule set IDs",
        "save": "Save",
        "cancel": "Cancel",
        "new": "New",
        "jieba": "Advanced Jieba",
        "unavailable": "unavailable on this host",
        "skipped_files": "Corrupt profiles skipped: {files}",
    },
    "zh-Hans": {
        "title": "配置方案",
        "name": "名称",
        "config": "转换",
        "rules": "规则集 ID",
        "save": "保存",
        "cancel": "取消",
        "new": "新建",
        "jieba": "高级 Jieba",
        "unavailable": "本机不可用",
        "skipped_files": "已跳过损坏的方案文件：{files}",
    },
    "zh-Hant": {
        "title": "設定檔",
        "name": "名稱",
        "config": "轉換",
        "rules": "規則集 ID",
        "save": "儲存",
        "cancel": "取消",
        "new": "新增",
        "jieba": "進階 Jieba",
        "unavailable": "此主機不可用",
        "skipped_files": "已略過損毀的設定檔：{files}",
    },
}
STANDARD_CONFIGS = V1_CONFIGS


def _labels(translator: Any) -> dict[str, str]:
    return _LABELS.get(getattr(translator, "language", "en"), _LABELS["en"])


def show_profile_window(
    profiles: Iterable[Profile],
    *,
    translator: Any = None,
    store: ProfileStore | None = None,
    selected_id: str | None = None,
    available_configs: Iterable[str] | None = None,
    storage_errors: Iterable[str] = (),
) -> Profile | None:
    qt = _load_qt_widgets()
    _ensure_application(qt)
    values = tuple(profiles)
    dialog = ProfileManagerDialog(
        qt,
        values,
        translator=translator,
        store=store,
        selected_id=selected_id,
        available_configs=available_configs,
        storage_errors=storage_errors,
    )
    exec_method = getattr(dialog.dialog, "exec", None) or dialog.dialog.exec_
    exec_method()
    return dialog.selected if dialog.accepted else None


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
        storage_errors: Iterable[str] = (),
    ) -> None:
        self._qt = qt_widgets
        self._labels = _labels(translator)
        self._profiles = list(profiles)
        self._store = store
        self._storage_errors = tuple(storage_errors)
        available = tuple(SUPPORTED_CONFIGS if available_configs is None else available_configs)
        self._available_configs = _base_config_options(available)
        self._available_config_ids = set(available)
        self._jieba_configs = {base: config for base, config in JIEBA_CONFIG_BY_BASE.items()
                               if config in self._available_config_ids}
        self._loading = False
        self.selected: Profile | None = None
        self.accepted = False
        self.dialog = qt_widgets.QDialog()
        self.dialog.setWindowTitle(self._labels["title"])
        self.dialog.resize(520, 300)
        self._build()
        index = next(
            (i for i, profile in enumerate(self._profiles) if profile.id == selected_id), 0
        )
        if self._profiles:
            self.combo.setCurrentIndex(index)
        self._load()

    def _build(self) -> None:
        qt = self._qt
        layout = qt.QVBoxLayout(self.dialog)
        if self._storage_errors:
            notice = qt.QLabel(self._labels["skipped_files"].format(
                files=", ".join(self._storage_errors)))
            notice.setWordWrap(True)
            layout.addWidget(notice)
        self.combo = qt.QComboBox()
        for profile in self._profiles:
            self.combo.addItem(profile.name or profile.id, profile.id)
        layout.addWidget(self.combo)
        form = qt.QFormLayout()
        self.name_edit = qt.QLineEdit()
        self.config_combo = qt.QComboBox()
        for config in self._available_configs:
            self.config_combo.addItem(config, config)
        self.jieba_checkbox = qt.QCheckBox(self._labels["jieba"])
        self.rules_edit = qt.QLineEdit()
        form.addRow(self._labels["name"], self.name_edit)
        form.addRow(self._labels["config"], self.config_combo)
        form.addRow(self.jieba_checkbox)
        form.addRow(self._labels["rules"], self.rules_edit)
        layout.addLayout(form)
        buttons = qt.QHBoxLayout()
        self.new_button = qt.QPushButton(self._labels["new"])
        self.save_button = qt.QPushButton(self._labels["save"])
        self.cancel_button = qt.QPushButton(self._labels["cancel"])
        for button in (self.new_button, self.save_button, self.cancel_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.combo.currentIndexChanged.connect(self._load)
        self.config_combo.currentIndexChanged.connect(self._config_changed)
        self.new_button.clicked.connect(self._new)
        self.save_button.clicked.connect(self._save)
        self.cancel_button.clicked.connect(self.dialog.reject)

    def _load(self) -> None:
        index = self.combo.currentIndex()
        if index < 0 or index >= len(self._profiles):
            return
        profile = self._profiles[index]
        self.name_edit.setText(profile.name)
        self._loading = True
        conversion = profile.conversion
        if conversion in BASE_CONFIG_BY_JIEBA:
            base = BASE_CONFIG_BY_JIEBA[conversion]
            if conversion not in self._available_config_ids:
                config_index = self.config_combo.findData(conversion)
                if config_index < 0:
                    self.config_combo.addItem(
                        f"{conversion} ({self._labels['unavailable']})", conversion)
                    config_index = self.config_combo.findData(conversion)
                if config_index >= 0:
                    self.config_combo.setCurrentIndex(config_index)
                self.jieba_checkbox.setChecked(False)
                self.jieba_checkbox.setEnabled(False)
                self.jieba_checkbox.setToolTip(self._labels["unavailable"])
            else:
                config_index = self.config_combo.findData(base)
                if config_index >= 0:
                    self.config_combo.setCurrentIndex(config_index)
                self.jieba_checkbox.setChecked(True)
                self.jieba_checkbox.setEnabled(True)
                self.jieba_checkbox.setToolTip("")
        else:
            config_index = self.config_combo.findData(conversion)
            if config_index < 0:
                self.config_combo.addItem(
                    f"{conversion} ({self._labels['unavailable']})", conversion)
                config_index = self.config_combo.findData(conversion)
            if config_index >= 0:
                self.config_combo.setCurrentIndex(config_index)
            plugin = JIEBA_CONFIG_BY_BASE.get(conversion)
            self.jieba_checkbox.setChecked(False)
            self.jieba_checkbox.setEnabled(plugin in self._available_config_ids)
            self.jieba_checkbox.setToolTip("")
        self.rules_edit.setText(",".join(profile.ruleset_ids))
        self._loading = False

    def _new(self) -> None:
        profile = Profile(name="New profile")
        self._profiles.append(profile)
        self.combo.addItem(profile.name, profile.id)
        self.combo.setCurrentIndex(len(self._profiles) - 1)
        self._load()

    def _save(self) -> None:
        index = self.combo.currentIndex()
        if index < 0 or index >= len(self._profiles):
            self._new()
            index = self.combo.currentIndex()
        old = self._profiles[index]
        try:
            conversion = _profile_conversion(
                self.config_combo, self.jieba_checkbox, self._jieba_configs, old.conversion)
            profile = replace(
                old,
                name=self.name_edit.text().strip(),
                conversion=conversion,
                segmentation="jieba" if conversion.endswith("_jieba") else "mmseg",
                ruleset_ids=tuple(
                    item.strip() for item in self.rules_edit.text().split(",") if item.strip()
                ),
            )
            if not profile.name:
                raise ProfileValidationError("name must be a non-empty string")
            self._profiles[index] = profile
            if self._store is not None:
                self._store.save(profile)
            self.selected = profile
            self.accepted = True
            self.dialog.accept()
        except (ProfileValidationError, ValueError) as exc:
            self._qt.QMessageBox.warning(self.dialog, self._labels["title"], str(exc))

    def _config_changed(self, *_args):
        if self._loading:
            return
        config = self.config_combo.currentData()
        if config in BASE_CONFIG_BY_JIEBA:
            self.jieba_checkbox.setChecked(False)
            self.jieba_checkbox.setEnabled(False)
            self.jieba_checkbox.setToolTip(self._labels["unavailable"])
            return
        plugin = JIEBA_CONFIG_BY_BASE.get(config)
        available = plugin in self._available_config_ids
        self.jieba_checkbox.setChecked(False)
        self.jieba_checkbox.setEnabled(available)
        self.jieba_checkbox.setToolTip("" if available else self._labels["unavailable"])


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
    seen.update(BASE_CONFIG_BY_JIEBA[value] for value in values if value in BASE_CONFIG_BY_JIEBA)
    return tuple(config for config in V1_CONFIGS if config in seen)


def _profile_conversion(config_combo, jieba_checkbox, jieba_configs, original):
    selected = config_combo.currentData()
    if not isinstance(selected, str) or not selected:
        return original
    if selected in BASE_CONFIG_BY_JIEBA:
        return selected
    return jieba_configs.get(selected, selected) if jieba_checkbox.isChecked() else selected


def _ensure_application(qt: Any) -> Any:
    global _application
    app = qt.QApplication.instance()
    if app is None:
        import sys

        app = qt.QApplication(sys.argv)
    _application = app
    return app


__all__ = ["ProfileManagerDialog", "STANDARD_CONFIGS", "show_profile_window"]
