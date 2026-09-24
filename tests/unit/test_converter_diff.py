from itertools import combinations
import random
import time

import pytest

from core.converter import OfficialBackendConverter
from core.diff import bounded_opcodes
from core.models import ConvertRequest
from core.planner import build_conversion_plan
from core.staging import apply_changes
from document.tokenizer import tokenize_xhtml
from opencc_backend.backend import OpenCCBackend


class _Backend:
    def __init__(self, target: str):
        self.target = target
        self.calls = []

    def convert(self, text: str) -> str:
        self.calls.append(text)
        return self.target


def _reconstruct(source: str, target: str, opcodes) -> str:
    source_cursor = 0
    target_cursor = 0
    target_fragments = []
    for tag, i1, i2, j1, j2 in opcodes:
        assert i1 == source_cursor
        assert j1 == target_cursor
        target_fragments.append(target[j1:j2])
        source_cursor = i2
        target_cursor = j2
        if tag == "equal":
            assert source[i1:i2] == target[j1:j2]
    assert source_cursor == len(source)
    assert target_cursor == len(target)
    return "".join(target_fragments)


def test_short_diff_keeps_character_level_preview_detail():
    source = "甲乙丙丁"
    target = "甲乙X丁"

    result = OfficialBackendConverter(_Backend(target)).convert(
        source, ConvertRequest(config="s2t")
    )

    assert [(change.source, change.target, change.span.start, change.span.end) for change in result.changes] == [
        ("丙", "X", 2, 3)
    ]


def test_backend_receives_the_complete_source_once():
    source = "汉" * 6_000
    backend = _Backend("漢" * 6_000)

    OfficialBackendConverter(backend).convert(source, ConvertRequest(config="s2t"))

    assert backend.calls == [source]


def test_large_pathological_text_uses_fast_coarse_fallback_and_reconstructs():
    source = "汉" * 6_000
    target = "漢" * 6_000

    started = time.perf_counter()
    opcodes = bounded_opcodes(source, target)
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0
    assert opcodes == (("replace", 0, len(source), 0, len(target)),)
    assert _reconstruct(source, target, opcodes) == target


def test_random_inputs_reconstruct_without_overlapping_source_spans():
    rng = random.Random(20260922)
    alphabet = "汉字繁體abc🙂e\u0301"
    for _ in range(200):
        source = "".join(rng.choice(alphabet) for _ in range(rng.randrange(80)))
        target = "".join(rng.choice(alphabet) for _ in range(rng.randrange(80)))
        opcodes = bounded_opcodes(source, target)
        assert _reconstruct(source, target, opcodes) == target
        previous_end = 0
        for tag, i1, i2, j1, j2 in opcodes:
            assert i1 >= previous_end
            assert i1 <= i2 <= len(source)
            assert j1 <= j2 <= len(target)
            previous_end = i2


def test_edge_cases_include_insert_delete_astral_and_combining_text():
    cases = (
        ("", "漢"),
        ("漢", ""),
        ("A🙂e\u0301", "A😄é"),
        ("甲甲甲甲", "甲X甲甲甲"),
    )
    for source, target in cases:
        opcodes = bounded_opcodes(source, target)
        assert _reconstruct(source, target, opcodes) == target


@pytest.mark.parametrize(
    ("source", "target"),
    (
        ("打印机", "印表機"),
        ("激光打印机坏了", "雷射印表機壞了"),
        ("鼠标和内存", "滑鼠和記憶體"),
    ),
)
def test_regional_phrase_is_one_change(source, target):
    opcodes = bounded_opcodes(source, target)

    assert len([opcode for opcode in opcodes if opcode[0] != "equal"]) == 1
    assert _reconstruct(source, target, opcodes) == target


def test_partial_acceptance_never_mixes_phrase():
    source = "<p>打印机</p>"
    backend = OpenCCBackend("s2twp")
    try:
        plan = build_conversion_plan(
            file_id="a",
            source=source,
            document=tokenize_xhtml(source),
            backend=backend,
            request=ConvertRequest("s2twp"),
        )
    finally:
        backend.close()

    for size in range(len(plan.changes) + 1):
        for accepted in combinations(plan.changes, size):
            converted = apply_changes(source, accepted)
            paragraph = converted.removeprefix("<p>").removesuffix("</p>")
            assert paragraph in {"打印机", "印表機"}


def test_opcodes_partition_both_strings():
    cases = [
        ("打印机", "印表機"),
        ("激光打印机坏了", "雷射印表機壞了"),
        ("鼠标和内存", "滑鼠和記憶體"),
        ("后面还有", "後面還有"),
    ]
    rng = random.Random(20260924)
    alphabet = "汉字繁體abc🙂e\u0301"
    cases.extend(
        (
            "".join(rng.choice(alphabet) for _ in range(rng.randrange(30))),
            "".join(rng.choice(alphabet) for _ in range(rng.randrange(30))),
        )
        for _ in range(50)
    )
    for source, target in cases:
        assert _reconstruct(source, target, bounded_opcodes(source, target)) == target


def test_equal_length_uses_positional_opcodes():
    assert bounded_opcodes("后面还有", "後面還有") == (
        ("replace", 0, 1, 0, 1),
        ("equal", 1, 2, 1, 2),
        ("replace", 2, 3, 2, 3),
        ("equal", 3, 4, 3, 4),
    )
    source, target = "面包资源后面还", "麪包資源後面還"
    changed = [opcode for opcode in bounded_opcodes(source, target) if opcode[0] != "equal"]
    assert [(source[i1:i2], target[j1:j2]) for _tag, i1, i2, j1, j2 in changed] == [
        ("面", "麪"), ("资", "資"), ("后", "後"), ("还", "還")
    ]


def test_equal_length_random_inputs_partition_and_reconstruct():
    rng = random.Random(20260924)
    alphabet = "汉字繁體abc🙂e\u0301"
    for _ in range(200):
        size = rng.randrange(80)
        source = "".join(rng.choice(alphabet) for _ in range(size))
        target = "".join(rng.choice(alphabet) for _ in range(size))
        opcodes = bounded_opcodes(source, target)
        assert _reconstruct(source, target, opcodes) == target
        assert all(i2 - i1 == j2 - j1 for _tag, i1, i2, j1, j2 in opcodes)


def test_very_large_unchanged_edges_do_not_become_one_giant_preview_change():
    source = '前' * 150_000 + '汉' + '后' * 150_000
    target = '前' * 150_000 + '漢' + '后' * 150_000
    changed = [op for op in bounded_opcodes(source, target) if op[0] != 'equal']
    assert changed == [('replace', 150_000, 150_001, 150_000, 150_001)]
