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
    """Resize ``window`` from a saved positive integer pair or use ``default``."""

    saved = _valid_size(preferences.get(key)) if isinstance(preferences, Mapping) else None
    window.resize(*(saved or default))


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
