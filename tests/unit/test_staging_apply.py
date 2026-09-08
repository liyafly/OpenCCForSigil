import random

import pytest

from core.models import SourceSpan, TokenChange
from core.staging import StagingError, _validate_source_changes, apply_changes


def _change(source: str, start: int, end: int, target: str, change_id: str) -> TokenChange:
    return TokenChange(
        source=source[start:end],
        target=target,
        span=SourceSpan(start, end),
        rule_source="test",
        change_id=change_id,
    )


def _baseline_apply(source: str, changes: tuple[TokenChange, ...]) -> str:
    _validate_source_changes(source, changes)
    result = source
    for change in sorted(
        changes,
        key=lambda item: (item.span.start, item.span.end),
        reverse=True,
    ):
        result = result[: change.span.start] + change.target + result[change.span.end :]
    return result


def _random_changes(rng: random.Random, source: str) -> tuple[TokenChange, ...]:
    changes = []
    cursor = 0
    change_index = 0
    while cursor < len(source):
        if rng.random() < 0.35:
            changes.append(_change(source, cursor, cursor, rng.choice(("", "插", "🙂")), str(change_index)))
            change_index += 1
        if rng.random() < 0.7:
            width = rng.randint(1, min(4, len(source) - cursor))
            end = cursor + width
            changes.append(
                _change(source, cursor, end, rng.choice(("", "X", "漢字", "🙂")), str(change_index))
            )
            change_index += 1
            cursor = end
        else:
            cursor += rng.randint(1, min(3, len(source) - cursor))
    if rng.random() < 0.5:
        changes.append(_change(source, len(source), len(source), rng.choice(("", "尾", "!")), str(change_index)))
    rng.shuffle(changes)
    return tuple(changes)


def test_apply_changes_matches_previous_right_to_left_assembly_for_random_valid_patches():
    rng = random.Random(20260908)
    for _ in range(200):
        source = "a汉🙂b界c"
        changes = _random_changes(rng, source)
        assert apply_changes(source, changes) == _baseline_apply(source, changes)


def test_apply_changes_preserves_boundary_insertions_deletions_and_adjacent_patches():
    assert apply_changes(
        "ab",
        (
            _change("ab", 0, 1, "X", "replace"),
            _change("ab", 0, 0, "I", "insert-at-start"),
        ),
    ) == "IXb"
    assert apply_changes(
        "ab",
        (
            _change("ab", 1, 2, "Y", "replace-right"),
            _change("ab", 1, 1, "I", "insert-between"),
            _change("ab", 0, 1, "X", "replace-left"),
        ),
    ) == "XIY"
    assert apply_changes(
        "a汉🙂b",
        (
            _change("a汉🙂b", 1, 3, "", "delete"),
            _change("a汉🙂b", 4, 4, "尾", "insert-at-end"),
        ),
    ) == "ab尾"


@pytest.mark.parametrize(
    "changes",
    (
        (
            _change("abc", 0, 2, "X", "outer"),
            _change("abc", 1, 3, "Y", "overlap"),
        ),
        (
            _change("abc", 0, 3, "X", "replace"),
            _change("abc", 1, 1, "I", "insert-inside"),
        ),
        (
            _change("abc", 1, 1, "I", "insert-one"),
            _change("abc", 1, 1, "J", "insert-two"),
        ),
    ),
)
def test_apply_changes_rejects_overlapping_or_duplicate_insertion_spans(
    changes: tuple[TokenChange, ...],
):
    with pytest.raises(StagingError, match="overlapping change spans"):
        apply_changes("abc", changes)
