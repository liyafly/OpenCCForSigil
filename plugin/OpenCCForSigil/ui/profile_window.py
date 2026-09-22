"""Small functional profile picker/editor with three-language labels."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable

from app.profiles import Profile, ProfileStore, ProfileValidationError
from rules.precedence import base_direction


_LABELS = {
    "en": {
        "title": "Profiles",
        "name": "Name",
        "config": "Conversion",
        "rules": "Rule set IDs",
        "save": "Save",
        "cancel": "Cancel",
        "new": "New",
    },
    "zh-Hans": {
        "title": "配置方案",
        "name": "名称",
        "config": "转换",
        "rules": "规则集 ID",
        "save": "保存",
        "cancel": "取消",
        "new": "新建",
    },
    "zh-Hant": {
        "title": "設定檔",
        "name": "名稱",
        "config": "轉換",
        "rules": "規則集 ID",
        "save": "儲存",
        "cancel": "取消",
        "new": "新增",
    },
}
STANDARD_CONFIGS = (
    "s2t",
    "t2s",
    "s2tw",
    "tw2s",
    "s2twp",
    "tw2sp",
    "s2hk",
    "hk2s",
    "s2hkp",
    "hk2sp",
    "t2tw",
    "tw2t",
    "t2hk",
    "hk2t",
    "t2jp",
    "jp2t",
)


def _labels(translator: Any) -> dict[str, str]:
    return _LABELS.get(getattr(translator, "language", "en"), _LABELS["en"])


def show_profile_window(
    profiles: Iterable[Profile],
    *,
    translator: Any = None,
    store: ProfileStore | None = None,
    selected_id: str | None = None,
    available_configs: Iterable[str] | None = None,
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
    ) -> None:
        self._qt = qt_widgets
        self._labels = _labels(translator)
        self._profiles = list(profiles)
        self._store = store
        self._available_configs = _base_config_options(available_configs)
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
        self.combo = qt.QComboBox()
        for profile in self._profiles:
            self.combo.addItem(profile.name or profile.id, profile.id)
        layout.addWidget(self.combo)
        form = qt.QFormLayout()
        self.name_edit = qt.QLineEdit()
        self.config_combo = qt.QComboBox()
        for config in self._available_configs:
            self.config_combo.addItem(config, config)
        self.rules_edit = qt.QLineEdit()
        form.addRow(self._labels["name"], self.name_edit)
        form.addRow(self._labels["config"], self.config_combo)
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
        self.new_button.clicked.connect(self._new)
        self.save_button.clicked.connect(self._save)
        self.cancel_button.clicked.connect(self.dialog.reject)

    def _load(self) -> None:
        index = self.combo.currentIndex()
        if index < 0 or index >= len(self._profiles):
            return
        profile = self._profiles[index]
        self.name_edit.setText(profile.name)
        self.config_combo.setCurrentIndex(self.config_combo.findData(profile.conversion))
        self.rules_edit.setText(",".join(profile.ruleset_ids))

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
            profile = replace(
                old,
                name=self.name_edit.text().strip(),
                conversion=str(self.config_combo.currentData()),
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
    values = STANDARD_CONFIGS if available_configs is None else available_configs
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        direction = base_direction(str(value))
        if direction in STANDARD_CONFIGS and direction not in seen:
            seen.add(direction)
            result.append(direction)
    return tuple(result)


def _ensure_application(qt: Any) -> Any:
    global _application
    app = qt.QApplication.instance()
    if app is None:
        import sys

        app = qt.QApplication(sys.argv)
    _application = app
    return app


__all__ = ["ProfileManagerDialog", "STANDARD_CONFIGS", "show_profile_window"]
