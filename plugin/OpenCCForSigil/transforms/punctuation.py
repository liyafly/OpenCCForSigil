"""Horizontal punctuation normalization boundary.

Only presentation-form punctuation with a stable horizontal counterpart is
normalized.  Vertical writing-mode behavior is intentionally rejected here;
it requires document/CSS context and is outside the V1 transform API.
"""

from typing import Final


PUNCTUATION_MODES: Final[tuple[str, ...]] = ("keep", "horizontal")
_VERTICAL_MODES: Final[frozenset[str]] = frozenset(
    ("vertical", "vertical_compat", "vertical_compatible", "vertical_compatibility")
)
_MODE_ALIASES: Final[dict[str, str]] = {
    "horizontal_standard": "horizontal",
    "horizontal_compat": "horizontal",
}

# Unicode vertical presentation forms mapped to their ordinary horizontal
# punctuation counterparts.  Do not normalize ordinary full-width Chinese
# punctuation: its horizontal form is already the conventional glyph.
HORIZONTAL_PUNCTUATION_MAP: Final[dict[str, str]] = {
    "︐": ",",
    "︑": "、",
    "︒": "。",
    "︓": ":",
    "︔": ";",
    "︕": "!",
    "︖": "?",
    "︗": "〖",
    "︘": "〗",
    "︙": "…",
    "︵": "(",
    "︶": ")",
    "︷": "{",
    "︸": "}",
    "︹": "〔",
    "︺": "〕",
    "︻": "【",
    "︼": "】",
    "︽": "《",
    "︾": "》",
    "︿": "〈",
    "﹀": "〉",
    "﹁": "「",
    "﹂": "」",
    "﹃": "『",
    "﹄": "』",
    "︱": "—",
    "︲": "–",
    "︳": "_",
    "︴": "_",
}


def normalize_punctuation(text: str, mode: str = "keep") -> str:
    """Apply the selected horizontal punctuation policy to ``text``."""

    if mode in _VERTICAL_MODES:
        raise ValueError("vertical punctuation mode is not supported in V1")
    mode = _MODE_ALIASES.get(mode, mode)
    if mode not in PUNCTUATION_MODES:
        raise ValueError(f"unsupported punctuation mode: {mode!r}")
    if mode == "keep" or not text:
        return text
    return "".join(HORIZONTAL_PUNCTUATION_MAP.get(char, char) for char in text)


def transform_punctuation(text: str, mode: str = "keep") -> str:
    """Compatibility alias for :func:`normalize_punctuation`."""

    return normalize_punctuation(text, mode)


__all__ = [
    "HORIZONTAL_PUNCTUATION_MAP",
    "PUNCTUATION_MODES",
    "normalize_punctuation",
    "transform_punctuation",
]
