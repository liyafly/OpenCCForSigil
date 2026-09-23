from ui.preview_window import _ScopeDialog


class _Signal:
    def __init__(self):
        self.callback = None

    def connect(self, callback):
        self.callback = callback

    def emit(self, value=None):
        if self.callback is not None:
            self.callback(value)


class _Widget:
    def __init__(self, *_args):
        self.visible = True
        self.tooltip = ""
        self.hidden = 0

    def hide(self):
        self.visible = False
        self.hidden += 1

    def setWordWrap(self, _value):
        pass

    def setToolTip(self, value):
        self.tooltip = value


class _Layout:
    def __init__(self, parent=None):
        self.widgets = []
        if parent is not None:
            parent.layout = self

    def addWidget(self, widget, *_args):
        self.widgets.append(widget)


class _CheckBox(_Widget):
    def __init__(self, *args):
        super().__init__(*args)
        self.toggled = _Signal()


class _PushButton(_Widget):
    def __init__(self, *args):
        super().__init__(*args)
        self.clicked = _Signal()


class _Qt:
    QWidget = _Widget
    QLabel = _Widget
    QCheckBox = _CheckBox
    QPushButton = _PushButton
    QHBoxLayout = _Layout


class _Translator:
    def text(self, key):
        return key


def test_checkpoint_banner_visibility_and_hide_preference_callback():
    dialog = object.__new__(_ScopeDialog)
    dialog._checkpoint_notice_hidden = False
    calls = []
    dialog._hide_checkpoint_notice_callback = lambda: calls.append("hidden")

    hidden_layout = _Layout()
    dialog._build_checkpoint_banner(_Qt, hidden_layout, _Translator(), False)
    assert dialog.checkpoint_banner is None
    assert hidden_layout.widgets == []

    visible_layout = _Layout()
    dialog._build_checkpoint_banner(_Qt, visible_layout, _Translator(), True)
    assert dialog.checkpoint_banner.visible
    assert dialog.checkpoint_notice_label is visible_layout.widgets[0].layout.widgets[0]

    dialog._checkpoint_notice_preference_changed(False)
    dialog._checkpoint_notice_preference_changed(True)
    dialog._checkpoint_notice_preference_changed(True)

    assert calls == ["hidden"]
    assert not dialog.checkpoint_banner.visible
