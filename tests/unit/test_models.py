from dataclasses import replace

import pytest

from core.models import SourceSpan, TokenChange
from document.tokenizer import tokenize_xhtml
from opencc_backend.configs import (
    JIEBA_CONFIGS,
    V1_CONFIGS,
    comparison_configs,
    validate_config,
)
from ui.preview_window import CONFIG_SELECTION_ORDER


def test_source_span_is_half_open_and_non_negative():
    assert SourceSpan(2, 5).end == 5
    with pytest.raises(ValueError):
        SourceSpan(-1, 2)
    with pytest.raises(ValueError):
        SourceSpan(3, 2)


def test_change_models_use_slots():
    span = SourceSpan(0, 1)
    change = TokenChange("旧", "新", span, "test")

    assert not hasattr(span, "__dict__")
    assert not hasattr(change, "__dict__")
    assert SourceSpan(0, 1) == span
    assert hash(SourceSpan(0, 1)) == hash(span)
    assert TokenChange("旧", "新", span, "test") == change
    updated = replace(change, target="改")
    assert updated.target == "改" and updated.span is change.span and not hasattr(updated, "__dict__")


def test_text_target_does_not_carry_unused_context():
    source = "<p>文本目标</p>"

    document = tokenize_xhtml(source)

    assert len(document.targets) == 1
    assert document.targets[0].source_text == "文本目标"
    assert not hasattr(document.targets[0], "context")


def test_native_config_allowlist_and_comparison_metadata():
    assert len(V1_CONFIGS) == 16
    assert {"tw2s", "tw2sp", "hk2s", "hk2sp", "t2jp", "jp2t"} <= set(V1_CONFIGS)
    assert CONFIG_SELECTION_ORDER == V1_CONFIGS
    assert all("jieba" not in config for config in CONFIG_SELECTION_ORDER)
    assert JIEBA_CONFIGS == (
        "s2t_jieba",
        "s2tw_jieba",
        "s2twp_jieba",
        "s2hk_jieba",
        "s2hkp_jieba",
        "tw2sp_jieba",
        "hk2sp_jieba",
    )
    assert validate_config("s2t") == "s2t"
    assert validate_config("s2t_jieba") == "s2t_jieba"
    assert comparison_configs("s2twp") == ("s2t", "s2tw", "s2twp")
    assert comparison_configs("s2twp_jieba") == ("s2twp", "s2twp_jieba")
    with pytest.raises(Exception):
        validate_config("not_an_opencc_config")
