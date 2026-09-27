"""Small helpers for restoring and persisting top-level dialog sizes."""

from collections.abc import Mapping
from typing import Any, Callable


def _valid_size(value: Any) -> tuple[int, int] | None:
    if (not isinstance(value, (tuple, list)) or len(value) != 2
            or any(not isinstance(item, int) or isinstance(item, bool) or item <= 0
                   for item in value)):
        return None
    return int(value[0]), int(value[1])


def restore_window_size(
    window: Any,
    preferences: Mapping[str, Any] | None,
    key: str,
    default: tuple[int, int],
) -> None:
    """Restore a preferred size, bounded by the window's current screen."""

    saved = _valid_size(preferences.get(key)) if isinstance(preferences, Mapping) else None
    desired = saved or _valid_size(default) or (780, 500)
    screen = None
    screen_getter = getattr(window, "screen", None)
    if callable(screen_getter):
        screen = screen_getter()
    if screen is None:
        application = getattr(window, "windowHandle", None)
        handle = application() if callable(application) else None
        handle_screen = getattr(handle, "screen", None)
        screen = handle_screen() if callable(handle_screen) else None
    if screen is None:
        # Fake widgets and pre-parented dialogs may not expose their screen.
        qt = getattr(window, "_qt", None)
        application_type = getattr(qt, "QApplication", None)
        instance = getattr(application_type, "instance", None)
        app = instance() if callable(instance) else None
        primary = getattr(app, "primaryScreen", None)
        screen = primary() if callable(primary) else None
    geometry_getter = getattr(screen, "availableGeometry", None)
    geometry = geometry_getter() if callable(geometry_getter) else None
    width_getter = getattr(geometry, "width", None)
    height_getter = getattr(geometry, "height", None)
    if callable(width_getter) and callable(height_getter):
        max_width = max(1, width_getter() - 32)
        max_height = max(1, height_getter() - 32)
        desired = min(desired[0], max_width), min(desired[1], max_height)
    window.resize(*desired)


def save_window_size(
    window: Any,
    key: str,
    save_preferences: Callable[[dict[str, list[int]]], Any] | None,
) -> bool:
    """Send a single size preference to the caller if it can be read safely."""

    if not callable(save_preferences):
        return False
    size_getter = getattr(window, "size", None)
    size = size_getter() if callable(size_getter) else None
    width_getter = getattr(size, "width", None)
    height_getter = getattr(size, "height", None)
    if not callable(width_getter) or not callable(height_getter):
        return False
    value = _valid_size((width_getter(), height_getter()))
    if value is None:
        return False
    save_preferences({key: [value[0], value[1]]})
    return True
