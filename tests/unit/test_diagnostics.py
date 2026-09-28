import random

from core.converter import OfficialBackendConverter
from core.diagnostics import _is_han, diagnose_mixed_script
from core.models import ConvertRequest


def test_short_or_non_han_text_skips_diagnostic_backend_calls():
    calls = []

    def convert(_config, text):
        calls.append(text)
        return text

    result = diagnose_mixed_script("abc > !", convert)

    assert result.status == "unknown"
    assert result.evidence_length == 0
    assert not calls


def test_han_evidence_matches_character_reference():
    rng = random.Random(20260928)
    ranges = (
        (0x3400, 0x4DBF),
        (0x4E00, 0x9FFF),
        (0xF900, 0xFAFF),
        (0x20000, 0x2FA1F),
    )
    alphabet = "abc 中文。🙂"
    texts = ["".join(rng.choice(alphabet) for _ in range(rng.randrange(80)))
             for _ in range(200)]
    texts.extend(
        "".join(chr(rng.randrange(start, end + 1)) for _ in range(80))
        for start, end in ranges
    )
    texts.extend(
        "".join(chr(rng.randrange(start, end + 1)) if index % 2 else "a"
                for index in range(80))
        for start, end in ranges
    )

    for text in texts:
        result = diagnose_mixed_script(text, lambda _config, value: value)
        expected = sum(char.isalpha() and _is_han(char) for char in text)
        assert result.evidence_length == expected


def test_s2t_diagnosis_reuses_official_output_and_calls_only_t2s():
    class Backend:
        config = "s2t"

        def __init__(self):
            self.comparison_calls = []

        def convert(self, text):
            return text.replace("汉", "漢")

        def convert_for_config(self, config, text):
            self.comparison_calls.append(config)
            if config == "s2t":
                return text.replace("汉", "漢")
            if config == "t2s":
                return text.replace("漢", "汉")
            raise AssertionError(config)

    backend = Backend()
    request = ConvertRequest("s2t", diagnose_mixed=True, detailed_classification=False)

    result = OfficialBackendConverter(backend).convert("汉漢", request)

    assert result.target == "漢漢"
    assert backend.comparison_calls == ["t2s"]
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["MIXED_SCRIPT"]


def test_ascii_conversion_does_not_run_mixed_script_diagnosis():
    class Backend:
        config = "s2t"

        def __init__(self):
            self.comparison_calls = []

        def convert(self, text):
            return text

        def convert_for_config(self, config, text):
            self.comparison_calls.append(config)
            return text

    backend = Backend()
    OfficialBackendConverter(backend).convert("plain text 123", ConvertRequest("s2t"))

    assert backend.comparison_calls == []


def test_force_pivot_does_not_reuse_chained_output_as_a_direct_config_output():
    class Backend:
        config = "s2t"

        def convert(self, text):
            return self.convert_for_config("s2t", text)

        def convert_for_config(self, config, text):
            if config == "t2s":
                return text.replace("裡面", "里面")
            if config == "s2t":
                return text.replace("里面", "裏面")
            raise AssertionError(config)

    backend = Backend()
    source = "裡面"
    direct = OfficialBackendConverter(backend).convert(
        source, ConvertRequest("s2t", detailed_classification=False))
    pivoted = OfficialBackendConverter(backend).convert(
        source,
        ConvertRequest("s2t", pivot_chain=("t2s", "s2t"),
                       detailed_classification=False),
    )

    assert [item.code for item in pivoted.diagnostics] == [
        item.code for item in direct.diagnostics
    ]
    assert "MIXED_SCRIPT" not in [item.code for item in pivoted.diagnostics]
