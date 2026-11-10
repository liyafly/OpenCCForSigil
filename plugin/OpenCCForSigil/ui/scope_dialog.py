"""Scope selection dialog and its inventory helpers."""

from __future__ import annotations

from typing import Any
from collections.abc import Sequence

from sigil.scope import Scope, ScopeSelectionError, TextFile, resolve_target_selection
from ui.qt import enum_value as _enum_value
from ui.i18n import (
    SUPPORTED_LANGUAGES,
    Translator,
    plugin_window_title,
)


def _selected_xhtml_ids_and_ignored(
    adapter: Any,
    inventory: tuple[TextFile, ...],
) -> tuple[tuple[str, ...], int]:
    selected_iter = getattr(adapter, "selected_ids", None)
    if not callable(selected_iter):
        return (), 0
    known_ids = {item.file_id for item in inventory}
    selected = tuple(selected_iter())
    return (
        tuple(file_id for file_id in selected if file_id in known_ids),
        sum(file_id not in known_ids for file_id in selected),
    )


def _spine_ids(adapter: Any) -> tuple[str, ...]:
    """Read the spine manifest ids without reading any document content."""

    text_files = getattr(adapter, "text_files", None)
    if not callable(text_files):
        return ()
    try:
        return tuple(file_id for file_id, _href in text_files(Scope.SPINE))
    except (AttributeError, TypeError, ValueError):
        return ()


def _ordered_scope_inventory(
    inventory: Sequence[TextFile], spine_ids: Sequence[str]
) -> tuple[TextFile, ...]:
    """Show spine resources in reading order and other XHTML paths afterward."""

    spine_order = {file_id: index for index, file_id in enumerate(spine_ids)}
    return tuple(sorted(
        inventory,
        key=lambda item: (
            0 if item.file_id in spine_order else 1,
            spine_order.get(item.file_id, 0),
            "" if item.file_id in spine_order else item.href,
        ),
    ))


def _recovery_notice_text(kind: str, value: str, translator: Translator) -> str:
    key = {
        "preferences_corrupt": "recovery.preferences_corrupt",
        "preferences_future_schema": "recovery.preferences_future_schema",
        "profile_recovered": "recovery.profile_recovered",
        "profile_future_schema": "recovery.profile_future_schema",
        "rulesets_missing": "recovery.rulesets_missing",
        "rulesets_future_schema": "recovery.rulesets_future_schema",
        "rulesets_recovered": "recovery.rulesets_recovered",
    }.get(kind, "recovery.generic")
    if kind == "profile_recovered":
        return translator.text(
            key, value=value, name=translator.text("profile.default_name"))
    return translator.text(key, value=value)


def _information_icon_label(qt_widgets: Any, parent: Any, translator: Translator) -> Any:
    label = qt_widgets.QLabel()
    set_accessible_name = getattr(label, "setAccessibleName", None)
    if callable(set_accessible_name):
        set_accessible_name(translator.text("a11y.scope.information"))
    style_type = getattr(qt_widgets, "QStyle", None)
    pixmap_type = getattr(style_type, "StandardPixmap", style_type)
    information_type = getattr(pixmap_type, "SP_MessageBoxInformation", None)
    style_getter = getattr(parent, "style", None)
    style = style_getter() if callable(style_getter) else None
    standard_icon = getattr(style, "standardIcon", None)
    if information_type is not None and callable(standard_icon):
        icon = standard_icon(information_type)
        pixmap = getattr(icon, "pixmap", None)
        set_pixmap = getattr(label, "setPixmap", None)
        if callable(pixmap) and callable(set_pixmap):
            set_pixmap(pixmap(20, 20))
            return label
    set_text = getattr(label, "setText", None)
    if callable(set_text):
        set_text("ℹ")
    return label


def _set_scope_banner_surface(banner: Any, qt_widgets: Any) -> None:
    object_name = "openccForSigilScopeNoticeBanner"
    set_object_name = getattr(banner, "setObjectName", None)
    if callable(set_object_name):
        set_object_name(object_name)
    palette_getter = getattr(banner, "palette", None)
    palette = palette_getter() if callable(palette_getter) else None
    gui = getattr(qt_widgets, "QtGui", None)
    palette_type = getattr(gui, "QPalette", None)
    role = _enum_value(palette_type, "AlternateBase")
    if role is None:
        role = _enum_value(palette_type, "Base")
    color_getter = getattr(palette, "color", None)
    if role is None or not callable(color_getter):
        return
    try:
        color = color_getter(role)
    except (TypeError, ValueError):
        return
    name_getter = getattr(color, "name", None)
    color_name = name_getter() if callable(name_getter) else None
    if not isinstance(color_name, str) or not color_name:
        return
    set_style_sheet = getattr(banner, "setStyleSheet", None)
    if callable(set_style_sheet):
        set_style_sheet(
            f"QWidget#{object_name} {{ background-color: {color_name}; }}")


class _ScopeDialog:
    """Qt view for selecting targets; all content reads happen after it closes."""

    def __init__(
        self,
        qt_widgets: Any,
        inventory: tuple[TextFile, ...],
        initial_ids: tuple[str, ...],
        language: str,
        translator: Translator,
        *,
        ignored_non_xhtml: int = 0,
        spine_ids: tuple[str, ...] = (),
        nav_id: str | None = None,
        recovery_notices=(),
        initial_scope: Scope | None = None,
        embedded=True,
        container=None,
        parent_dialog=None,
    ) -> None:
        self._qt = qt_widgets
        self._inventory = inventory
        self._translator = translator
        if not embedded:
            raise ValueError("Scope selection must be embedded in the combined chooser")
        self._language_changed_callback = None
        self._analysis_enabled_callback = None
        self.accepted = False
        self.selection = None
        self.language = language
        self.ignored_non_xhtml = max(0, ignored_non_xhtml)
        self.spine_ids = tuple(file_id for file_id in spine_ids if file_id)
        self.nav_id = nav_id
        self._manual_selection_ids = set(initial_ids)
        self._recovery_notices = tuple(recovery_notices)
        self._updating_items = False
        self.dialog = parent_dialog or qt_widgets.QDialog()
        layout = qt_widgets.QVBoxLayout(container or self.dialog)
        self.recovery_notice_label = None
        self.recovery_notice_banner = None
        self.recovery_notice_icon_label = None
        if self._recovery_notices:
            notice_lines = [
                _recovery_notice_text(kind, value, translator)
                for kind, value in self._recovery_notices
            ]
            self.recovery_notice_banner = qt_widgets.QWidget()
            recovery_layout = qt_widgets.QHBoxLayout(self.recovery_notice_banner)
            self.recovery_notice_icon_label = _information_icon_label(
                qt_widgets, self.recovery_notice_banner, translator)
            recovery_layout.addWidget(self.recovery_notice_icon_label)
            self.recovery_notice_label = qt_widgets.QLabel("\n".join(notice_lines))
            self.recovery_notice_label.setWordWrap(True)
            recovery_layout.addWidget(self.recovery_notice_label, 1)
            _set_scope_banner_surface(self.recovery_notice_banner, qt_widgets)
            layout.addWidget(self.recovery_notice_banner)
        self.language_label = qt_widgets.QLabel(translator.text("language.label"))
        self.language_combo = qt_widgets.QComboBox()
        self.language_label.setBuddy(self.language_combo)
        self.language_label.setAccessibleName(translator.text("a11y.scope.language"))
        for code in SUPPORTED_LANGUAGES:
            self.language_combo.addItem(self._translator.text(f"language.name.{code}"), code)
        self.language_combo.setCurrentIndex(max(0, self.language_combo.findData(language)))
        self.language_combo.currentIndexChanged.connect(self._language_changed)

        self.selected_radio = qt_widgets.QRadioButton(translator.text("scope.selected"))
        self.spine_radio = qt_widgets.QRadioButton(translator.text("scope.spine"))
        self.all_radio = qt_widgets.QRadioButton(translator.text("scope.all"))
        self.selected_radio.setChecked(True)
        radio_row = qt_widgets.QHBoxLayout()
        for radio in (self.selected_radio, self.spine_radio, self.all_radio):
            radio_row.addWidget(radio)
            radio.toggled.connect(self._refresh_enabled)
        layout.addLayout(radio_row)

        self.filter_edit = qt_widgets.QLineEdit()
        self.filter_edit.setPlaceholderText(translator.text("scope.filter"))
        self.filter_edit.setAccessibleName(translator.text("a11y.scope.filter_files"))
        self.filter_edit.textChanged.connect(self._refresh_list)
        self.filter_edit.returnPressed.connect(self._focus_first_visible_item)
        self._install_filter_enter_guard(qt_widgets)
        layout.addWidget(self.filter_edit)
        self.guide_label = qt_widgets.QLabel(translator.text("scope.selection_guide"))
        self.guide_label.setWordWrap(True)
        self.guide_label.setVisible(not bool(initial_ids))
        layout.addWidget(self.guide_label)
        self.list_widget = qt_widgets.QListWidget()
        self.list_widget.setAccessibleName(translator.text("a11y.scope.file_list"))
        elide_middle = _enum_value(qt_widgets.Qt, "ElideMiddle")
        if elide_middle is not None:
            self.list_widget.setTextElideMode(elide_middle)
        layout.addWidget(self.list_widget)
        action_row = qt_widgets.QHBoxLayout()
        self.select_visible = qt_widgets.QPushButton(translator.text("scope.select_visible"))
        self.clear_visible = qt_widgets.QPushButton(translator.text("scope.clear_visible"))
        self.select_visible.setAutoDefault(False)
        self.clear_visible.setAutoDefault(False)
        action_row.addWidget(self.select_visible)
        action_row.addWidget(self.clear_visible)
        action_row.addStretch(1)
        layout.addLayout(action_row)
        self.count_label = qt_widgets.QLabel()
        layout.addWidget(self.count_label)
        self.ignored_label = qt_widgets.QLabel()
        self.ignored_label.setWordWrap(True)
        layout.addWidget(self.ignored_label)

        self.select_visible.clicked.connect(lambda: self._set_visible(True))
        self.clear_visible.clicked.connect(lambda: self._set_visible(False))

        initial = set(initial_ids)
        for item in inventory:
            label = self._scope_item_label(item)
            row = qt_widgets.QListWidgetItem(label)
            row.setToolTip(item.href)
            row.setData(qt_widgets.Qt.UserRole, item.file_id)
            row.setFlags(row.flags() | qt_widgets.Qt.ItemIsUserCheckable)
            row.setCheckState(
                qt_widgets.Qt.Checked if item.file_id in initial else qt_widgets.Qt.Unchecked
            )
            self.list_widget.addItem(row)
        self.list_widget.itemChanged.connect(self._item_changed)
        current_row_changed = getattr(self.list_widget, "currentRowChanged", None)
        if current_row_changed is not None:
            current_row_changed.connect(self._current_row_changed)
        if initial_scope is Scope.SPINE:
            self.spine_radio.setChecked(True)
        elif initial_scope is Scope.ALL_XHTML:
            self.all_radio.setChecked(True)
        else:
            self.selected_radio.setChecked(True)
        self._refresh_enabled()
        self._refresh_count()

    def _focus_first_visible_item(self) -> None:
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            if not item.isHidden():
                self.list_widget.setCurrentRow(row)
                self.list_widget.setFocus()
                return

    def _filter_enter_pressed(self) -> bool:
        self._focus_first_visible_item()
        return True

    def _install_filter_enter_guard(self, qt_widgets: Any) -> None:
        core = getattr(qt_widgets, "QtCore", None)
        qobject = getattr(core, "QObject", None)
        qevent = getattr(core, "QEvent", None)
        if qobject is None or qevent is None:
            return
        key_press = getattr(qevent, "KeyPress", None)
        if key_press is None:
            key_press = getattr(getattr(qevent, "Type", qevent), "KeyPress", None)
        keys = {
            _enum_value(qt_widgets.Qt, "Key_Return"),
            _enum_value(qt_widgets.Qt, "Key_Enter"),
        }
        keys.discard(None)
        if key_press is None or not keys:
            return
        owner = self

        class _Guard(qobject):
            def eventFilter(_self, _target, event):
                return (event.type() == key_press and event.key() in keys
                        and owner._filter_enter_pressed())

        self._filter_enter_guard = _Guard(self.filter_edit)
        self.filter_edit.installEventFilter(self._filter_enter_guard)

    def _item_changed(self, _item: Any) -> None:
        """Refresh counts and validity for direct checkbox changes."""
        if self._updating_items:
            return
        if self.selected_radio.isChecked():
            self._manual_selection_ids = set(self._checked_ids())
        elif self.all_radio.isChecked() or self.spine_radio.isChecked():
            self._refresh_mode_items()
        self._refresh_count()
        self._update_analyze_enabled()

    def _current_row_changed(self, row: int) -> None:
        self._refresh_count()
        self._update_analyze_enabled()

    def _language_changed(self) -> None:
        code = str(self.language_combo.currentData())
        self.language = code
        self._translator.set_language(code)
        self.dialog.setWindowTitle(plugin_window_title(
            self._translator, self._translator.text("main.title")))
        self.language_label.setText(self._translator.text("language.label"))
        self.language_label.setAccessibleName(self._translator.text("a11y.scope.language"))
        self.guide_label.setText(self._translator.text("scope.selection_guide"))
        for row, item in enumerate(self._inventory):
            self.list_widget.item(row).setText(self._scope_item_label(item))
        if self.recovery_notice_label is not None and self.recovery_notice_label.isVisible():
            self.recovery_notice_label.setText("\n".join(
                _recovery_notice_text(kind, value, self._translator)
                for kind, value in self._recovery_notices
            ))
            set_accessible_name = getattr(
                self.recovery_notice_icon_label, "setAccessibleName", None)
            if callable(set_accessible_name):
                set_accessible_name(self._translator.text("a11y.scope.information"))
        self.selected_radio.setText(self._translator.text("scope.selected"))
        self.spine_radio.setText(self._translator.text("scope.spine"))
        self.all_radio.setText(self._translator.text("scope.all"))
        self.filter_edit.setPlaceholderText(self._translator.text("scope.filter"))
        self.filter_edit.setAccessibleName(self._translator.text("a11y.scope.filter_files"))
        self.list_widget.setAccessibleName(self._translator.text("a11y.scope.file_list"))
        self.select_visible.setText(self._translator.text("scope.select_visible"))
        self.clear_visible.setText(self._translator.text("scope.clear_visible"))
        self._refresh_count()
        self._update_analyze_enabled()
        if callable(self._language_changed_callback):
            self._language_changed_callback()

    def _scope_item_label(self, item: TextFile) -> str:
        label = item.href
        if item.file_id == self.nav_id:
            label += " " + self._translator.text("scope.navigation_suffix")
        return label

    def _checked_ids(self) -> tuple[str, ...]:
        checked = self._qt.Qt.Checked
        return tuple(
            self.list_widget.item(index).data(self._qt.Qt.UserRole)
            for index in range(self.list_widget.count())
            if self.list_widget.item(index).checkState() == checked
        )

    def selected_ids(self) -> tuple[str, ...]:
        if self.all_radio.isChecked():
            return tuple(item.file_id for item in self._inventory)
        if self.spine_radio.isChecked():
            available = {item.file_id for item in self._inventory}
            return tuple(file_id for file_id in self.spine_ids if file_id in available)
        return tuple(item.file_id for item in self._inventory
                     if item.file_id in self._manual_selection_ids)

    def _refresh_list(self) -> None:
        query = self.filter_edit.text().strip().lower()
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            item.setHidden(bool(query) and query not in item.text().lower())
        self._refresh_count()

    def _set_visible(self, checked: bool) -> None:
        if not self.selected_radio.isChecked():
            return
        state = self._qt.Qt.Checked if checked else self._qt.Qt.Unchecked
        self.list_widget.blockSignals(True)
        try:
            for index in range(self.list_widget.count()):
                item = self.list_widget.item(index)
                if not item.isHidden():
                    item.setCheckState(state)
        finally:
            self.list_widget.blockSignals(False)
        self._manual_selection_ids = set(self._checked_ids())
        self._refresh_count()
        self._update_analyze_enabled()

    def _refresh_count(self) -> None:
        total = self.list_widget.count()
        selected = len(self.selected_ids())
        visible = sum(not self.list_widget.item(index).isHidden()
                      for index in range(total))
        self.count_label.setText(self._translator.text(
            "scope.selection_count", selected=selected, total=total, visible=visible))
        if self.ignored_non_xhtml:
            self.ignored_label.setText(
                self._translator.text(
                    "scope.ignored_non_xhtml", count=self.ignored_non_xhtml
                )
            )
            self.ignored_label.show()
        else:
            self.ignored_label.clear()
            self.ignored_label.hide()

    def _refresh_enabled(self) -> None:
        custom = self.selected_radio.isChecked()
        self.filter_edit.setEnabled(True)
        self.list_widget.setEnabled(True)
        self.select_visible.setEnabled(custom)
        self.clear_visible.setEnabled(custom)
        self.spine_radio.setEnabled(bool(self.spine_ids))
        self._refresh_mode_items()
        self._refresh_count()
        self._update_analyze_enabled()

    def _refresh_mode_items(self) -> None:
        mode = ("spine" if self.spine_radio.isChecked() else
                "all" if self.all_radio.isChecked() else "selected")
        qt = self._qt.Qt
        checkable = getattr(qt, "ItemIsUserCheckable", 16)
        self._updating_items = True
        self.list_widget.blockSignals(True)
        try:
            available = {item.file_id for item in self._inventory}
            fixed_ids = (set(self.spine_ids) & available if mode == "spine" else
                         available if mode == "all" else set())
            for index in range(self.list_widget.count()):
                item = self.list_widget.item(index)
                file_id = item.data(qt.UserRole)
                if mode == "selected":
                    item.setFlags(item.flags() | checkable)
                    checked = file_id in self._manual_selection_ids
                else:
                    item.setFlags(item.flags() & ~checkable)
                    checked = file_id in fixed_ids
                item.setCheckState(qt.Checked if checked else qt.Unchecked)
            self.guide_label.setVisible(
                mode == "selected" and not self._manual_selection_ids)
        finally:
            self.list_widget.blockSignals(False)
            self._updating_items = False

    def _update_analyze_enabled(self) -> None:
        callback = self._analysis_enabled_callback
        if callable(callback):
            callback()

    def _selection_is_valid(self) -> bool:
        count = len(self.selected_ids())
        valid = bool(self._inventory)
        if self.selected_radio.isChecked():
            valid = count > 0
        elif self.spine_radio.isChecked():
            valid = bool(self.spine_ids)
        return valid

    def _accept(self, *, close=True) -> None:
        try:
            scope = (
                Scope.ALL_XHTML if self.all_radio.isChecked()
                else Scope.SPINE if self.spine_radio.isChecked()
                else Scope.SELECTED
            )
            ids = self.spine_ids if scope is Scope.SPINE else self.selected_ids()
            selection = resolve_target_selection(self._inventory, scope, ids)
            if selection.empty:
                raise ScopeSelectionError(self._translator.text("scope.none"))
        except ScopeSelectionError:
            self._qt.QMessageBox.warning(
                self.dialog,
                plugin_window_title(
                    self._translator, self._translator.text("scope.title")),
                self._translator.text("scope.none"),
            )
            return
        self.scope = scope
        self.selection = selection
        self.accepted = True
        if close:
            self.dialog.accept()
