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

    return QuotationPairer(mode).feed(text)


class QuotationPairer:
    """Pair quotation marks while retaining state across source text spans.

    ``feed(..., mutate=False)`` is used for protected rule spans: the text is
    preserved while its quote marks still advance the pairing state.
    """

    __slots__ = ("mode", "in_quote", "ascii_unbalanced")

    def __init__(self, mode: str = "keep") -> None:
        self.mode = _canonical_mode(mode)
        self.in_quote = False
        self.ascii_unbalanced = False

    def feed(self, text: str, *, mutate: bool = True) -> str:
        if self.mode == "keep" or not text:
            return text

        opening, closing = QUOTATION_PAIRS[self.mode]
        result: list[str] = []
        for char in text:
            replacement = char
            if char == '"':
                self.ascii_unbalanced = not self.ascii_unbalanced
                replacement = closing if self.in_quote else opening
                self.in_quote = not self.in_quote
            elif char in _OPENING_QUOTES:
                replacement = opening
                self.in_quote = True
            elif char in _CLOSING_QUOTES:
                replacement = closing
                self.in_quote = False
            result.append(replacement if mutate else char)
        return "".join(result) if mutate else text


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
    "QuotationPairer",
    "convert_quotations",
    "transform_quotations",
]
