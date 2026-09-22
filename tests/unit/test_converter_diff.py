import random
import time

from core.converter import OfficialBackendConverter
from core.diff import bounded_opcodes
from core.models import ConvertRequest


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


def test_very_large_unchanged_edges_do_not_become_one_giant_preview_change():
    source = '前' * 150_000 + '汉' + '后' * 150_000
    target = '前' * 150_000 + '漢' + '后' * 150_000
    changed = [op for op in bounded_opcodes(source, target) if op[0] != 'equal']
    assert changed == [('replace', 150_000, 150_001, 150_000, 150_001)]
