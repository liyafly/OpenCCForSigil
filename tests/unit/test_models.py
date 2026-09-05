import pytest

from core.models import SourceSpan
from opencc_backend.configs import V1_CONFIGS, comparison_configs, validate_config


def test_source_span_is_half_open_and_non_negative():
    assert SourceSpan(2, 5).end == 5
    with pytest.raises(ValueError):
        SourceSpan(-1, 2)
    with pytest.raises(ValueError):
        SourceSpan(3, 2)


def test_native_config_allowlist_and_comparison_metadata():
    assert len(V1_CONFIGS) == 16
    assert validate_config("s2t") == "s2t"
    assert comparison_configs("s2twp") == ("s2t", "s2tw", "s2twp")
    with pytest.raises(Exception):
        validate_config("s2t_jieba")
