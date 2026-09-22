"""Deterministic quotation transforms.

Quotation handling is deliberately separate from OpenCC.  The default is a
byte-preserving ``keep`` mode; the other modes only select the requested pair
and are idempotent when applied again.
"""

from typing import Final


QUOTATION_MODES: Final[tuple[str, ...]] = ("keep", "curly", "corner", "nested_corner")
QUOTATION_PAIRS: Final[dict[str, tuple[str, str]]] = {
    "curly": ("“", "”"),
    "corner": ("「", "」"),
    "nested_corner": ("『", "』"),
}
_MODE_ALIASES: Final[dict[str, str]] = {
    "chinese_curly": "curly",
    "chinese_curved": "curly",
    "east_asian_corner": "corner",
    "nested": "nested_corner",
}

_OPENING_QUOTES: Final[frozenset[str]] = frozenset(("“", "「", "『"))
_CLOSING_QUOTES: Final[frozenset[str]] = frozenset(("”", "」", "』"))


def transform_quotations(text: str, mode: str = "keep") -> str:
    """Normalize double quotation marks to one explicit Chinese pair.

    ``keep`` returns the original object unchanged.  ASCII double quotes are
    paired deterministically from left to right; existing Chinese opening and
    closing forms retain their role.  Apostrophes and single quotation marks
    are left alone because they also serve as ordinary text punctuation.
    """

    mode = _canonical_mode(mode)
    if mode == "keep" or not text:
        return text

    opening, closing = QUOTATION_PAIRS[mode]
    in_quote = False
    result: list[str] = []
    for char in text:
        if char == '"':
            result.append(closing if in_quote else opening)
            in_quote = not in_quote
        elif char in _OPENING_QUOTES:
            result.append(opening)
            in_quote = True
        elif char in _CLOSING_QUOTES:
            result.append(closing)
            in_quote = False
        else:
            result.append(char)
    return "".join(result)


def convert_quotations(text: str, mode: str = "keep") -> str:
    """Compatibility alias for :func:`transform_quotations`."""

    return transform_quotations(text, mode)


def _validate_mode(mode: str) -> None:
    if mode not in QUOTATION_MODES and mode not in _MODE_ALIASES:
        raise ValueError(f"unsupported quotation mode: {mode!r}")


def _canonical_mode(mode: str) -> str:
    _validate_mode(mode)
    return _MODE_ALIASES.get(mode, mode)


__all__ = [
    "QUOTATION_MODES",
    "QUOTATION_PAIRS",
    "convert_quotations",
    "transform_quotations",
]
