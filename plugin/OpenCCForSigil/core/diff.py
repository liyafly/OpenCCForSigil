"""Bounded, source-relative string diffing for conversion previews.

The official backend still receives the complete source string exactly once.  This
module only aligns that already-computed target with the source so that preview
changes can be applied as source slices.

Short inputs use the historical character-level ``SequenceMatcher`` alignment.
For larger inputs, the algorithm first trims equal edges and looks for unique,
fixed-size exact anchors.  Only bounded gaps are sent to the detailed matcher;
an oversized or ambiguous gap becomes one replacement opcode.  The fallback
changes granularity only: its source and target slices still reconstruct the
exact backend result.
"""

from difflib import SequenceMatcher
from typing import Iterator


# The old matcher is useful for preview detail, but its worst case is
# quadratic.  Keeping this threshold small makes the expensive path explicit.
_DETAILED_LIMIT = 1_024
_ANCHOR_SIZES = (32, 16, 8)
_MAX_ANCHORS = 2_048
_MAX_DETAILED_WORK = 2_000_000
# Three linear anchor passes plus their position scans stay within a small,
# predictable amount of Python work.  Beyond this limit alignment detail is
# deliberately traded for a single exact replacement region.
_MAX_ALIGNMENT_CHARS = 250_000


Opcode = tuple[str, int, int, int, int]
__all__ = ["Opcode", "bounded_opcodes"]


def bounded_opcodes(source: str, target: str) -> tuple[Opcode, ...]:
    """Return deterministic opcodes with a bounded worst-case alignment cost.

    Offsets are relative to the arguments, matching ``SequenceMatcher``.  The
    result always partitions both strings, and every non-equal opcode carries
    the exact source and target slices for that region.  It is therefore safe
    for callers to use the opcodes as source patches even when alignment falls
    back to a coarse ``replace``. Equal-length text is compared by position;
    unequal-length changes separated by one equal character are merged so a
    phrase is not split into independently accepted changes.
    """

    if source == target:
        return (("equal", 0, len(source), 0, len(target)),) if source else ()
    if len(source) == len(target):
        return _positional_opcodes(source, target)
    if max(len(source), len(target)) <= _DETAILED_LIMIT:
        opcodes = tuple(_coalesce_opcodes(list(_detailed_opcodes(source, target))))
        return tuple(_merge_close_changes(opcodes, source, target))
    prefix = _common_prefix(source, target)
    source_end = len(source)
    target_end = len(target)
    suffix = _common_suffix(source, target, prefix, source_end, target_end)

    source_mid_end = source_end - suffix
    target_mid_end = target_end - suffix
    source_mid = source[prefix:source_mid_end]
    target_mid = target[prefix:target_mid_end]

    opcodes: list[Opcode] = []
    if prefix:
        opcodes.append(("equal", 0, prefix, 0, prefix))

    if source_mid or target_mid:
        if max(len(source_mid), len(target_mid)) > _MAX_ALIGNMENT_CHARS:
            middle = (_replacement_opcode(source_mid, target_mid, 0, 0),)
        elif max(len(source_mid), len(target_mid)) <= _DETAILED_LIMIT:
            middle = _detailed_opcodes(source_mid, target_mid)
        else:
            middle = _large_opcodes(source_mid, target_mid)
        opcodes.extend(_offset_opcodes(middle, prefix, prefix))

    if suffix:
        opcodes.append(("equal", source_mid_end, source_end, target_mid_end, target_end))
    coalesced = tuple(_coalesce_opcodes(opcodes))
    return tuple(_merge_close_changes(coalesced, source, target))


def _positional_opcodes(source: str, target: str) -> tuple[Opcode, ...]:
    """Diff equal-length strings by position, grouping adjacent differences.

    Consecutive differing characters form one ``replace`` opcode, which keeps
    an OpenCC phrase such as 打印机 -> 印表機 together.
    """

    opcodes = []
    index = 0
    length = len(source)
    while index < length:
        end = index
        same = source[index] == target[index]
        while end < length and (source[end] == target[end]) == same:
            end += 1
        opcodes.append(("equal" if same else "replace", index, end, index, end))
        index = end
    return tuple(opcodes)


def _merge_close_changes(
    opcodes: tuple[Opcode, ...], source: str, target: str
) -> tuple[Opcode, ...]:
    """Merge changes separated by at most one equal source character."""

    merged = []
    cursor = 0
    while cursor < len(opcodes):
        current = opcodes[cursor]
        if current[0] != "equal" and cursor + 2 < len(opcodes):
            equal = opcodes[cursor + 1]
            following = opcodes[cursor + 2]
            equal_source = source[equal[1]:equal[2]]
            equal_target = target[equal[3]:equal[4]]
            if (
                equal[0] == "equal"
                and len(equal_source) <= 1
                and equal_source == equal_target
                and following[0] != "equal"
            ):
                combined = ("replace", current[1], following[2], current[3], following[4])
                cursor += 3
                while cursor + 1 < len(opcodes):
                    equal = opcodes[cursor]
                    following = opcodes[cursor + 1]
                    equal_source = source[equal[1]:equal[2]]
                    equal_target = target[equal[3]:equal[4]]
                    if (
                        equal[0] != "equal"
                        or len(equal_source) > 1
                        or equal_source != equal_target
                        or following[0] == "equal"
                    ):
                        break
                    combined = ("replace", combined[1], following[2], combined[3], following[4])
                    cursor += 2
                merged.append(combined)
                continue
        merged.append(current)
        cursor += 1
    return tuple(merged)


def _detailed_opcodes(source: str, target: str) -> tuple[Opcode, ...]:
    return tuple(
        (tag, i1, i2, j1, j2)
        for tag, i1, i2, j1, j2 in SequenceMatcher(
            None, source, target, autojunk=False
        ).get_opcodes()
    )


def _large_opcodes(source: str, target: str) -> tuple[Opcode, ...]:
    """Align a large region using linear anchor passes and bounded gaps."""

    anchors = _find_anchors(source, target)
    if not anchors:
        return (_replacement_opcode(source, target, 0, 0),)

    opcodes: list[Opcode] = []
    source_cursor = 0
    target_cursor = 0
    detailed_work = 0
    for source_start, target_start, size in anchors:
        if source_start > source_cursor or target_start > target_cursor:
            source_gap = source[source_cursor:source_start]
            target_gap = target[target_cursor:target_start]
            gap_work = len(source_gap) * len(target_gap)
            allow_detailed = detailed_work + gap_work <= _MAX_DETAILED_WORK
            opcodes.extend(
                _gap_opcodes(
                    source_gap,
                    target_gap,
                    source_cursor,
                    target_cursor,
                    allow_detailed=allow_detailed,
                )
            )
            if allow_detailed and max(len(source_gap), len(target_gap)) <= _DETAILED_LIMIT:
                detailed_work += gap_work
        opcodes.append(
            (
                "equal",
                source_start,
                source_start + size,
                target_start,
                target_start + size,
            )
        )
        source_cursor = source_start + size
        target_cursor = target_start + size

    if source_cursor < len(source) or target_cursor < len(target):
        opcodes.extend(
            _gap_opcodes(
                source[source_cursor:],
                target[target_cursor:],
                source_cursor,
                target_cursor,
                allow_detailed=(
                    detailed_work
                    + len(source[source_cursor:]) * len(target[target_cursor:])
                    <= _MAX_DETAILED_WORK
                ),
            )
        )
    return tuple(_coalesce_opcodes(opcodes))


def _gap_opcodes(
    source: str,
    target: str,
    source_offset: int,
    target_offset: int,
    *,
    allow_detailed: bool = True,
) -> tuple[Opcode, ...]:
    if source == target:
        if not source:
            return ()
        return (
            (
                "equal",
                source_offset,
                source_offset + len(source),
                target_offset,
                target_offset + len(target),
            ),
        )
    if allow_detailed and max(len(source), len(target)) <= _DETAILED_LIMIT:
        return tuple(
            _offset_opcodes(
                _detailed_opcodes(source, target),
                source_offset,
                target_offset,
            )
        )
    return (_replacement_opcode(source, target, source_offset, target_offset),)


def _replacement_opcode(
    source: str,
    target: str,
    source_offset: int,
    target_offset: int,
) -> Opcode:
    if not source:
        tag = "insert"
    elif not target:
        tag = "delete"
    else:
        tag = "replace"
    return (
        tag,
        source_offset,
        source_offset + len(source),
        target_offset,
        target_offset + len(target),
    )


def _find_anchors(source: str, target: str) -> tuple[tuple[int, int, int], ...]:
    """Find monotonic unique exact windows without quadratic candidate search."""

    for size in _ANCHOR_SIZES:
        if len(source) < size or len(target) < size:
            continue
        source_counts = _window_counts(source, size)
        target_counts = _window_counts(target, size)
        source_positions = _unique_window_positions(source, size, source_counts)
        target_positions = _unique_window_positions(target, size, target_counts)
        if not source_positions or not target_positions:
            continue

        anchors: list[tuple[int, int, int]] = []
        source_cursor = 0
        target_cursor = 0
        for window, target_start in target_positions.items():
            source_start = source_positions.get(window)
            if source_start is None:
                continue
            if source_start < source_cursor or target_start < target_cursor:
                continue
            anchors.append((source_start, target_start, size))
            source_cursor = source_start + size
            target_cursor = target_start + size
            if len(anchors) >= _MAX_ANCHORS:
                break
        if anchors:
            return tuple(anchors)
    return ()


def _window_counts(text: str, size: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for start in range(len(text) - size + 1):
        window = text[start : start + size]
        counts[window] = counts.get(window, 0) + 1
    return counts


def _unique_window_positions(
    text: str,
    size: int,
    counts: dict[str, int],
) -> dict[str, int]:
    positions: dict[str, int] = {}
    for start in range(len(text) - size + 1):
        window = text[start : start + size]
        if counts.get(window) == 1:
            positions[window] = start
    return positions


def _common_prefix(source: str, target: str) -> int:
    limit = min(len(source), len(target))
    index = 0
    while index < limit and source[index] == target[index]:
        index += 1
    return index


def _common_suffix(
    source: str,
    target: str,
    prefix: int,
    source_end: int,
    target_end: int,
) -> int:
    limit = min(source_end - prefix, target_end - prefix)
    suffix = 0
    while suffix < limit and source[source_end - suffix - 1] == target[target_end - suffix - 1]:
        suffix += 1
    return suffix


def _offset_opcodes(
    opcodes: tuple[Opcode, ...] | list[Opcode],
    source_offset: int,
    target_offset: int,
) -> Iterator[Opcode]:
    for tag, i1, i2, j1, j2 in opcodes:
        yield (
            tag,
            i1 + source_offset,
            i2 + source_offset,
            j1 + target_offset,
            j2 + target_offset,
        )


def _coalesce_opcodes(opcodes: list[Opcode]) -> Iterator[Opcode]:
    previous: Opcode | None = None
    for opcode in opcodes:
        tag, source_start, source_end, target_start, target_end = opcode
        if source_start == source_end and target_start == target_end:
            continue
        if tag == "equal" and (source_start == source_end or target_start == target_end):
            continue
        if previous is not None:
            if (
                previous[0] == tag
                and previous[2] == source_start
                and previous[4] == target_start
            ):
                previous = (
                    tag,
                    previous[1],
                    source_end,
                    previous[3],
                    target_end,
                )
                continue
            yield previous
        previous = opcode
    if previous is not None:
        yield previous
