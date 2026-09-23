from core.converter import OfficialBackendConverter
from core.diagnostics import diagnose_mixed_script
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
