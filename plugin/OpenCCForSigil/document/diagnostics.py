"""Pure source-boundary diagnostics for tokenized XHTML."""

from __future__ import annotations

from bisect import bisect_left

from core.models import Diagnostic, SourceSpan
from document.tokenizer import TokenizedDocument


INLINE_ELEMENTS = frozenset(
    {
        "a",
        "b",
        "code",
        "em",
        "i",
        "mark",
        "rt",
        "ruby",
        "s",
        "small",
        "span",
        "strong",
        "sub",
        "sup",
        "u",
    }
)


def inline_boundary_diagnostics(
    document: TokenizedDocument,
) -> tuple[Diagnostic, ...]:
    """Report Han text targets separated by inline markup boundaries.

    Each target remains its own source span.  The diagnostic warns callers not
    to join the spans into one OpenCC segment across ``em``, ``ruby`` or other
    inline elements.
    """

    if not isinstance(document, TokenizedDocument):
        raise TypeError("inline boundary diagnostics require a TokenizedDocument")
    targets = tuple(sorted((target for target in document.targets if target.kind == "text"),
                           key=lambda target: target.source_start))
    tag_starts = [tag.start for tag in document.tags]
    diagnostics: list[Diagnostic] = []
    for previous, following in zip(targets, targets[1:]):
        if not _ends_with_han(previous.source_text) or not _starts_with_han(
            following.source_text
        ):
            continue
        tags = tuple(
            tag
            for tag in document.tags[bisect_left(tag_starts, previous.source_end):
                                     bisect_left(tag_starts, following.source_start)]
            if tag.end <= following.source_start
        )
        if not tags or not any(tag.name in INLINE_ELEMENTS for tag in tags):
            continue
        gap = document.source[previous.source_end : following.source_start]
        if not _contains_only_tags_and_space(gap, tags, gap_start=previous.source_end):
            continue
        diagnostics.append(
            Diagnostic(
                code="INLINE_BOUNDARY",
                message=(
                    "Han text targets are separated by inline markup; "
                    "conversion will not merge across this boundary"
                ),
                span=SourceSpan(previous.source_end, following.source_start),
            )
        )
    return tuple(diagnostics)


def inline_boundary_codes(document: TokenizedDocument) -> tuple[str, ...]:
    """Return deterministic diagnostic codes for a tokenized document."""

    return tuple(diagnostic.code for diagnostic in inline_boundary_diagnostics(document))


def find_inline_boundaries(document: TokenizedDocument) -> tuple[Diagnostic, ...]:
    """Compatibility alias for :func:`inline_boundary_diagnostics`."""

    return inline_boundary_diagnostics(document)


def _contains_only_tags_and_space(
    gap: str,
    tags: tuple[object, ...],
    *,
    gap_start: int,
) -> bool:
    cursor = 0
    for tag in tags:
        relative_start = tag.start - gap_start
        relative_end = tag.end - gap_start
        if gap[cursor:relative_start].strip():
            return False
        cursor = relative_end
    return not gap[cursor:].strip()


def _starts_with_han(text: str) -> bool:
    return bool(text) and _is_han(text[0])


def _ends_with_han(text: str) -> bool:
    return bool(text) and _is_han(text[-1])


def _is_han(character: str) -> bool:
    codepoint = ord(character)
    return any(
        start <= codepoint <= finish
        for start, finish in (
            (0x3400, 0x4DBF),
            (0x4E00, 0x9FFF),
            (0xF900, 0xFAFF),
            (0x20000, 0x2FA1F),
        )
    )


__all__ = [
    "INLINE_ELEMENTS",
    "find_inline_boundaries",
    "inline_boundary_codes",
    "inline_boundary_diagnostics",
]
