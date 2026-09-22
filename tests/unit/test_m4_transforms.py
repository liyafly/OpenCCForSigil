import pytest
import unicodedata

from core.classifier import classify_conversion
from core.diagnostics import diagnose_mixed_script
from core.transformation import apply_force_pivot
from transforms.punctuation import HORIZONTAL_PUNCTUATION_MAP, normalize_punctuation
from transforms.quotations import transform_quotations


def test_quotation_modes_keep_default_and_are_idempotent():
    source = '他说：“甲” and "乙"。'

    assert transform_quotations(source) == source
    for mode, expected in (
        ("curly", '他说：“甲” and “乙”。'),
        ("corner", '他说：「甲」 and 「乙」。'),
        ("nested_corner", '他说：『甲』 and 『乙』。'),
    ):
        converted = transform_quotations(source, mode)
        assert converted == expected
        assert transform_quotations(converted, mode) == converted


def test_horizontal_punctuation_is_deterministic_and_vertical_is_rejected():
    source = "︐︑︒︓︔︕︖ ︵甲︶ ︷乙︸ ﹁丙﹂"
    expected = ",、。:;!? (甲) {乙} 「丙」"

    assert normalize_punctuation(source) == source
    converted = normalize_punctuation(source, "horizontal")
    assert converted == expected
    assert normalize_punctuation(converted, "horizontal") == converted
    with pytest.raises(ValueError, match="vertical"):
        normalize_punctuation(source, "vertical")


def test_horizontal_map_matches_unicode_vertical_compatibility_decompositions():
    for vertical, horizontal in HORIZONTAL_PUNCTUATION_MAP.items():
        decomposition = unicodedata.decomposition(vertical).split()
        assert decomposition and decomposition[0] == "<vertical>"
        assert horizontal == "".join(chr(int(value, 16)) for value in decomposition[1:])


class _Official:
    def __init__(self):
        self.calls = []

    def __call__(self, config, text):
        self.calls.append((config, text))
        if config == "s2t":
            return text.replace("汉", "漢").replace("软", "軟").replace("件", "件")
        if config == "t2s":
            return text.replace("漢", "汉").replace("軟", "软").replace("體", "体")
        if config == "s2tw":
            return text.replace("汉", "漢").replace("软", "軟")
        if config == "s2twp":
            return text.replace("汉", "漢").replace("软", "軟").replace("件", "體")
        return text


def test_mixed_script_diagnostic_uses_independent_official_outputs():
    backend = _Official()

    assert diagnose_mixed_script("汉字", backend).status == "simplified"
    assert diagnose_mixed_script("漢字", backend).status == "traditional"
    assert diagnose_mixed_script("汉漢", backend).status == "mixed"
    assert diagnose_mixed_script("汉", backend).status == "unknown"
    assert backend.calls[:2] == [("s2t", "汉字"), ("t2s", "汉字")]


def test_force_pivot_requires_explicit_valid_chain_and_marks_high_risk():
    backend = _Official()

    unchanged = apply_force_pivot("漢件", ("t2s", "s2twp"), backend)
    assert unchanged.target == "漢件"
    assert unchanged.applied is False
    assert backend.calls == []

    result = apply_force_pivot("漢件", ("t2s", "s2twp"), backend, enabled=True)
    assert result.target == "漢體"
    assert result.risk == "HIGH"
    assert result.rule_source == "PivotChain:t2s→s2twp"
    assert backend.calls == [("t2s", "漢件"), ("s2twp", "汉件")]

    with pytest.raises(ValueError, match="unsupported"):
        apply_force_pivot("漢件", ("s2tw", "s2twp"), backend, enabled=True)


def test_comparative_classification_calls_each_config_on_original_input():
    backend = _Official()
    result = classify_conversion("软件", "s2twp", backend)

    assert result.final == "軟體"
    assert result.comparisons == (
        ("s2t", "軟件"),
        ("s2tw", "軟件"),
        ("s2twp", "軟體"),
    )
    assert result.changes[0].category == "regional"
    assert result.changes[0].rule_source == "OpenCC:s2twp"
    assert result.changes[0].attribution_method == "comparative_config_diff"
    assert result.changes[0].attribution_confidence == "high"
    assert all(text == "软件" for _, text in backend.calls)


def test_comparative_classification_preserves_frozen_final_target():
    backend = _Official()
    result = classify_conversion("软件", "s2twp", backend, final="軟件")

    assert result.final == "軟件"
    assert result.changes[0].category == "character"
