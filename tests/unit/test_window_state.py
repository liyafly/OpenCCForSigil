from ui.window_state import restore_window_size, save_window_size


class Window:
    def __init__(self):
        self.dimensions = (0, 0)

    def resize(self, width, height):
        self.dimensions = (width, height)

    def size(self):
        return Size(*self.dimensions)


class Size:
    def __init__(self, width, height):
        self._width = width
        self._height = height

    def width(self):
        return self._width

    def height(self):
        return self._height


def test_restore_window_size_uses_saved_or_default_dimensions():
    window = Window()

    restore_window_size(window, {"profiles_dialog_size": [900, 650]},
                        "profiles_dialog_size", (780, 500))
    assert window.dimensions == (900, 650)

    restore_window_size(window, {"profiles_dialog_size": [0, -1]},
                        "profiles_dialog_size", (780, 500))
    assert window.dimensions == (780, 500)


def test_save_window_size_writes_only_positive_integer_dimensions():
    window = Window()
    window.resize(901, 651)
    saved = []

    save_window_size(window, "profiles_dialog_size", saved.append)

    assert saved == [{"profiles_dialog_size": [901, 651]}]
