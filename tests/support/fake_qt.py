"""Permissive fake Qt emulating a few real-Qt signal semantics."""

import inspect
import sys
from types import SimpleNamespace


class Signal:
    def __init__(self):
        self.slots = []
        self.blocked_owner = None

    def connect(self, fn):
        self.slots.append(fn)

    def emit(self, *args):
        if self.blocked_owner is not None and self.blocked_owner._blocked:
            return
        for fn in list(self.slots):
            try:
                sig = inspect.signature(fn)
                params = [
                    p
                    for p in sig.parameters.values()
                    if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                ]
                var = any(p.kind == p.VAR_POSITIONAL for p in sig.parameters.values())
                call_args = args if var else args[: len(params)]
            except (TypeError, ValueError):
                call_args = args
            try:
                fn(*call_args)
            except Exception as exc:  # PySide prints slot exceptions
                print(f"[slot exception] {type(exc).__name__}: {exc}", file=sys.stderr)
                LOG.append(exc)


LOG = []


class Base:
    _signals = ()

    def __init__(self, *args, **kwargs):
        self._blocked = False
        self._visible = True
        self._enabled = True
        self._text = ""
        self._tooltip = ""
        self._plain_text = ""
        self.calls = []
        self.args = args
        for name in self._signals + (
            "clicked",
            "toggled",
            "stateChanged",
            "currentIndexChanged",
            "textChanged",
            "activated",
            "triggered",
            "timeout",
            "accepted",
            "rejected",
            "itemChanged",
            "currentRowChanged",
            "itemSelectionChanged",
            "doubleClicked",
            "currentTextChanged",
            "itemDoubleClicked",
            "cellDoubleClicked",
            "itemClicked",
        ):
            s = Signal()
            s.blocked_owner = self
            setattr(self, name, s)
        if args and isinstance(args[0], str):
            self._text = args[0]

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def rec(*a, **k):
            self.calls.append((name, a))
            return None

        return rec

    def blockSignals(self, b):
        old = self._blocked
        self._blocked = b
        return old

    def setVisible(self, v):
        self._visible = bool(v)

    def isVisible(self):
        return self._visible

    def isVisibleTo(self, _p=None):
        return self._visible

    def isHidden(self):
        return not self._visible

    def show(self):
        self._visible = True

    def hide(self):
        self._visible = False

    def setEnabled(self, v):
        self._enabled = bool(v)

    def isEnabled(self):
        return self._enabled

    def setText(self, t):
        self._text = t

    def text(self):
        return self._text

    def setToolTip(self, t):
        self._tooltip = t

    def toolTip(self):
        return self._tooltip

    def setPlainText(self, value):
        self._plain_text = str(value)

    def toPlainText(self):
        return self._plain_text

    def clear(self):
        self._text = ""
        self._plain_text = ""

    def setWidget(self, widget):
        self._widget = widget

    def widget(self):
        return getattr(self, "_widget", None)


class Dialog(Base):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.finished = Signal()
        self.result = None

    def done(self, result):
        self.result = result
        self._visible = False
        self.finished.emit(result)

    def accept(self):
        self.accepted.emit()
        self.done(1)

    def reject(self):
        self.rejected.emit()
        self.done(0)


class Timer(Base):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._active = False
        self._interval = 0

    def setInterval(self, interval):
        self._interval = int(interval)

    def start(self):
        self._active = True

    def stop(self):
        self._active = False

    def isActive(self):
        return self._active


class MessageButton:
    def __init__(self, label, role):
        self.label = label
        self.role = role


class MessageBox(Base):
    AcceptRole = 0
    RejectRole = 1
    ActionRole = 3
    Warning = 2
    Yes = 0x4000
    No = 0x10000
    response = "back"
    instances = []

    @classmethod
    def information(cls, *args):
        LOG.append(("information", args))

    @classmethod
    def warning(cls, *args):
        LOG.append(("warning", args))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.buttons = []
        self.default_button = None
        self.escape_button = None
        self._clicked_button = None
        type(self).instances.append(self)

    def addButton(self, label, role):
        button = MessageButton(label, role)
        self.buttons.append(button)
        return button

    def setDefaultButton(self, button):
        self.default_button = button

    def setEscapeButton(self, button):
        self.escape_button = button

    def clickedButton(self):
        return self._clicked_button

    def exec(self):
        if type(self).response == "escape":
            self.press_escape()
        elif self.buttons:
            self._clicked_button = (
                self.buttons[0] if type(self).response == "back" else self.buttons[-1]
            )

    def press_escape(self):
        self._clicked_button = self.escape_button or next(
            (button for button in self.buttons if button.role == self.RejectRole),
            self.default_button,
        )


class Layout(Base):
    def __init__(self, parent=None, *a):
        super().__init__()
        self.children = []
        self.parent = parent
        if parent is not None and isinstance(parent, Base):
            parent._layout = self

    def addWidget(self, w, *a):
        self.children.append(w)

    def addLayout(self, layout, *a):
        self.children.append(layout)

    def insertWidget(self, i, w, *a):
        self.children.insert(i, w)

    def insertLayout(self, i, layout, *a):
        self.children.insert(i, layout)

    def addStretch(self, *a):
        self.children.append("<stretch>")

    def addRow(self, *a):
        self.children.append(a)

    def count(self):
        return len(self.children)


class Check(Base):
    def __init__(self, *a):
        super().__init__(*a)
        self._checked = False
        self._checkable = True
        self.group = None

    def setChecked(self, v):
        v = bool(v)
        if v == self._checked:
            return
        self._checked = v
        if v and self.group is not None:
            for other in self.group:
                if other is not self and other._checked:
                    other._checked = False
                    other.toggled.emit(False)
        self.toggled.emit(v)
        self.stateChanged.emit(2 if v else 0)

    def isChecked(self):
        return self._checked

    def setCheckable(self, v):
        self._checkable = v

    def click(self):
        self.setChecked(not self._checked) if self._checkable else None
        self.clicked.emit(self._checked)


RADIO_GROUP = []


class Radio(Check):
    def __init__(self, *a):
        super().__init__(*a)
        RADIO_GROUP.append(self)
        self.group = RADIO_GROUP

    def click(self):
        self.setChecked(True)
        self.clicked.emit(True)


class Button(Check):
    def __init__(self, *a):
        super().__init__(*a)
        self._checkable = False
        self.default = False
        self.auto_default = None

    def setDefault(self, v):
        self.default = v

    def setAutoDefault(self, v):
        self.auto_default = v

    def click(self):
        self.clicked.emit(False)


class SpinBox(Base):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._value = 0

    def setValue(self, value):
        self._value = int(value)

    def value(self):
        return self._value


class Combo(Base):
    def __init__(self, *a):
        super().__init__(*a)
        self.items = []
        self.index = -1

    def addItem(self, text, data=None):
        self.items.append([text, data])
        if self.index < 0:
            self.index = 0
            self.currentIndexChanged.emit(0)

    def insertSeparator(self, i):
        self.items.insert(i, ["<sep>", None])

    def clear(self):
        had = self.index >= 0
        self.items.clear()
        self.index = -1
        if had:
            self.currentIndexChanged.emit(-1)

    def count(self):
        return len(self.items)

    def findData(self, v):
        return next((i for i, it in enumerate(self.items) if it[1] == v and it[0] != "<sep>"), -1)

    def findText(self, t):
        return next((i for i, it in enumerate(self.items) if it[0] == t), -1)

    def currentData(self, role=None):
        return self.items[self.index][1] if 0 <= self.index < len(self.items) else None

    def currentText(self):
        return self.items[self.index][0] if 0 <= self.index < len(self.items) else ""

    def currentIndex(self):
        return self.index

    def itemData(self, i, role=None):
        return self.items[i][1]

    def itemText(self, i):
        return self.items[i][0]

    def setItemText(self, i, t):
        self.items[i][0] = t

    def setCurrentIndex(self, i):
        if i != self.index:
            self.index = i
            self.currentIndexChanged.emit(i)


class ListItem:
    def __init__(self, text=""):
        self._text = text
        self._data = {}
        self._flags = 1 | 32 | 16
        self._hidden = False
        self.list = None

    def text(self):
        return self._text

    def setText(self, t):
        self._text = t

    def setData(self, role, v):
        self._data[role] = v
        if self.list is not None and role == Qt.CheckStateRole:
            self.list.itemChanged.emit(self)

    def data(self, role):
        return self._data.get(role)

    def flags(self):
        return self._flags

    def setFlags(self, f):
        self._flags = f

    def setCheckState(self, s):
        self.setData(Qt.CheckStateRole, s)

    def checkState(self):
        return self._data.get(Qt.CheckStateRole)

    def setHidden(self, h):
        self._hidden = h

    def isHidden(self):
        return self._hidden

    def setToolTip(self, t):
        pass


class ListWidget(Base):
    def __init__(self, *a):
        super().__init__(*a)
        self._items = []
        self.row = -1

    def addItem(self, item):
        if isinstance(item, str):
            item = ListItem(item)
        item.list = self
        self._items.append(item)

    def item(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def count(self):
        return len(self._items)

    def currentRow(self):
        return self.row

    def setCurrentRow(self, r):
        if r != self.row:
            self.row = r
            self.currentRowChanged.emit(r)

    def clear(self):
        self._items.clear()
        self.row = -1


class TableWidget(Base):
    def __init__(self, rows=0, columns=0, *args):
        super().__init__(rows, columns, *args)
        self._rows = max(0, rows)
        self._columns = max(0, columns)
        self._items = {}
        self._current_row = -1

    def setRowCount(self, count):
        self._rows = max(0, int(count))
        self._items = {
            key: value for key, value in self._items.items() if key[0] < self._rows
        }
        if self._current_row >= self._rows:
            self._current_row = -1

    def rowCount(self):
        return self._rows

    def columnCount(self):
        return self._columns

    def insertRow(self, row):
        self._rows += 1
        self._items = {
            (r + (r >= row), c): item for (r, c), item in self._items.items()
        }

    def setItem(self, row, column, item):
        self._items[(row, column)] = item

    def item(self, row, column):
        return self._items.get((row, column))

    def currentRow(self):
        return self._current_row

    def selectRow(self, row):
        self._current_row = row

    def horizontalHeader(self):
        return Base()


class Qt:
    UserRole = 256
    CheckStateRole = 10
    DisplayRole = 0
    EditRole = 2
    ToolTipRole = 3
    ForegroundRole = 9
    FontRole = 6
    Checked = 2
    Unchecked = 0
    PartiallyChecked = 1
    ItemIsUserCheckable = 16
    ItemIsSelectable = 1
    ItemIsEnabled = 32
    ItemIsEditable = 2
    Horizontal = 1
    Vertical = 2
    WidgetWithChildrenShortcut = 1
    WindowCloseButtonHint = 0x8000000
    Key_Escape = 0x1000000
    ToolButtonTextBesideIcon = 2
    DownArrow = 2
    RightArrow = 4
    AscendingOrder = 0
    DescendingOrder = 1


def make():
    RADIO_GROUP.clear()
    qt = SimpleNamespace()
    for name in (
        "QLabel",
        "QWidget",
        "QPlainTextEdit",
        "QTextEdit",
        "QLineEdit",
        "QScrollArea",
        "QGroupBox",
        "QMenu",
        "QTableView",
        "QTableWidget",
        "QToolButton",
        "QSplitter",
        "QFrame",
        "QProgressDialog",
        "QListView",
        "QTreeWidget",
        "QDialogButtonBox",
        "QAction",
        "QShortcut",
        "QTableWidgetItem",
        "QTabWidget",
    ):
        setattr(qt, name, type(name, (Base,), {}))
    qt.QDialog = Dialog
    for name in ("QVBoxLayout", "QHBoxLayout", "QFormLayout", "QGridLayout"):
        setattr(qt, name, type(name, (Layout,), {}))
    qt.QCheckBox = type("QCheckBox", (Check,), {})
    qt.QRadioButton = type("QRadioButton", (Radio,), {})
    qt.QPushButton = type("QPushButton", (Button,), {})
    qt.QComboBox = type("QComboBox", (Combo,), {})
    qt.QSpinBox = SpinBox
    qt.QListWidget = type("QListWidget", (ListWidget,), {})
    qt.QTableWidget = type("QTableWidget", (TableWidget,), {})
    qt.QListWidgetItem = ListItem
    qt.Qt = Qt
    qt.QKeySequence = lambda s: s
    qt.QApplication = SimpleNamespace(
        instance=lambda: object(),
        processEvents=lambda: None,
        clipboard=lambda: SimpleNamespace(setText=lambda t: None),
    )
    qt.QMessageBox = MessageBox
    qt.QAbstractItemView = SimpleNamespace(
        SelectRows=1, SingleSelection=1, NoEditTriggers=0, ExtendedSelection=3
    )
    qt.QHeaderView = SimpleNamespace(ResizeToContents=3, Stretch=1, Interactive=0)
    qt.QtGui = SimpleNamespace(
        QAction=qt.QAction,
        QColor=lambda c: c,
        QFont=type("QFont", (Base,), {}),
        QShortcut=qt.QShortcut,
        QKeySequence=qt.QKeySequence,
    )
    qt.QTimer = Timer
    qt.QtCore = SimpleNamespace(QTimer=qt.QTimer, QObject=Base)
    qt.QShortcut = qt.QShortcut
    return qt


def tree(layout, depth=0, out=None):
    out = [] if out is None else out
    for c in getattr(layout, "children", []):
        if isinstance(c, Layout):
            out.append("  " * depth + type(c).__name__)
            tree(c, depth + 1, out)
        elif isinstance(c, Base):
            out.append("  " * depth + f"{type(c).__name__}({c._text!r})")
            if hasattr(c, "_layout"):
                tree(c._layout, depth + 1, out)
        else:
            out.append("  " * depth + repr(c)[:80])
    return out


class ModelIndex:
    def __init__(self, r=-1, c=-1):
        self._r, self._c = r, c

    def isValid(self):
        return self._r >= 0 and self._c >= 0

    def row(self):
        return self._r if self.isValid() else -1

    def column(self):
        return self._c


class AbstractTableModel:
    def __init__(self, parent=None):
        self.dataChanged = Signal()
        self.resets = 0
        self.data_changed = 0
        self.dataChanged.connect(lambda *a: setattr(self, "data_changed", self.data_changed + 1))

    def beginResetModel(self):
        pass

    def endResetModel(self):
        self.resets += 1
        view = getattr(self, "_view", None)
        if view is not None:
            view._reset()

    def index(self, r, c, parent=None):
        if 0 <= r < self.rowCount() and 0 <= c < self.columnCount():
            return ModelIndex(r, c)
        return ModelIndex()


class SelectionModel:
    def __init__(self):
        self.currentRowChanged = Signal()


class TableView(Base):
    def __init__(self, *a):
        super().__init__(*a)
        self._sel = SelectionModel()
        self._current = ModelIndex()
        self._model = None

    def setModel(self, m):
        self._model = m
        m._view = self

    def selectionModel(self):
        return self._sel

    def currentIndex(self):
        return self._current

    def setCurrentIndex(self, idx):
        prev = self._current
        if idx.row() != prev.row():
            self._current = idx
            self._sel.currentRowChanged.emit(idx, prev)
        else:
            self._current = idx

    def _reset(self):
        prev = self._current
        self._current = ModelIndex()
        if prev.row() != -1:
            self._sel.currentRowChanged.emit(self._current, prev)

    def horizontalHeader(self):
        return Base()

    def selectRow(self, r):
        pass

    def clearSelection(self):
        pass


def make_with_table():
    qt = make()
    qt.QtCore.QAbstractTableModel = AbstractTableModel
    qt.QTableView = TableView
    return qt


class ButtonBox(Base):
    StandardButton = type("SB", (), {"Cancel": 0x400000})
    ButtonRole = type("BR", (), {"ActionRole": 3, "AcceptRole": 0, "RejectRole": 1})

    def addButton(self, *a):
        b = Button(a[0] if isinstance(a[0], str) else f"<standard {a[0]:#x}>")
        self.__dict__.setdefault("kids", []).append((b, a[1:] if len(a) > 1 else ("standard",)))
        return b


_make_orig = make


def make():
    qt = _make_orig()
    qt.QDialogButtonBox = ButtonBox
    return qt
