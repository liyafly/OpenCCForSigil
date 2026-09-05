import pytest

from core.models import SourceSpan
from opencc_backend.configs import V1_CONFIGS, comparison_configs, validate_config
from ui.preview_window import CONFIG_SELECTION_ORDER


def test_source_span_is_half_open_and_non_negative():
    assert SourceSpan(2, 5).end == 5
    with pytest.raises(ValueError):
        SourceSpan(-1, 2)
    with pytest.raises(ValueError):
        SourceSpan(3, 2)


def test_native_config_allowlist_and_comparison_metadata():
    assert len(V1_CONFIGS) == 16
    assert {"tw2s", "tw2sp", "hk2s", "hk2sp", "t2jp", "jp2t"} <= set(V1_CONFIGS)
    assert CONFIG_SELECTION_ORDER == V1_CONFIGS
    assert all("jieba" not in config for config in CONFIG_SELECTION_ORDER)
    assert validate_config("s2t") == "s2t"
    assert comparison_configs("s2twp") == ("s2t", "s2tw", "s2twp")
    with pytest.raises(Exception):
        validate_config("s2t_jieba")
