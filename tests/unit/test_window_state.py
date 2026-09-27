import pytest

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


def test_restore_window_size_clamps_preference_to_associated_screen_without_drift():
    class Geometry:
        def width(self):
            return 800

        def height(self):
            return 600

    class Screen:
        def availableGeometry(self):
            return Geometry()

    class ScreenWindow(Window):
        def screen(self):
            return Screen()

    window = ScreenWindow()
    preferences = {"profiles_dialog_size": [4000, 3000]}
    for _ in range(100):
        restore_window_size(window, preferences, "profiles_dialog_size", (780, 500))

    assert window.dimensions == (768, 568)


@pytest.mark.parametrize("invalid", ([True, 400], ["900", 500], [], [0, 20], [-1, 20]))
def test_restore_window_size_rejects_invalid_saved_values(invalid):
    window = Window()
    restore_window_size(window, {"size": invalid}, "size", (780, 500))

    assert window.dimensions == (780, 500)
